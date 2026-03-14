#!/bin/bash
# =============================================================================
# deploy.sh — One-command deploy to Google Cloud Run
#
# Usage:
#   ./deploy.sh                         # uses current gcloud project + us-central1
#   REGION=us-east1 ./deploy.sh         # override region
#   GOOGLE_CLOUD_PROJECT=my-proj ./deploy.sh
#
# Prerequisites:
#   gcloud auth login
#   gcloud auth configure-docker REGION-docker.pkg.dev
#   gcloud services enable \
#     run.googleapis.com \
#     cloudbuild.googleapis.com \
#     artifactregistry.googleapis.com \
#     secretmanager.googleapis.com \
#     firestore.googleapis.com \
#     cloudtasks.googleapis.com
# =============================================================================

set -euo pipefail

# ── Config ────────────────────────────────────────────────────────────────────
PROJECT_ID="${GOOGLE_CLOUD_PROJECT:-$(gcloud config get-value project 2>/dev/null)}"
REGION="${REGION:-us-central1}"
API_SERVICE="voicevid-api"
WORKER_SERVICE="voicevid-worker"
RENDER_SERVICE="voicevid-render"
REPO="voicevid"
SHORT_SHA="$(git rev-parse --short HEAD 2>/dev/null || echo 'latest')"
API_IMAGE="$REGION-docker.pkg.dev/$PROJECT_ID/$REPO/api:$SHORT_SHA"
RENDER_IMAGE="$REGION-docker.pkg.dev/$PROJECT_ID/$REPO/render:$SHORT_SHA"
TASKS_QUEUE="video-generation"
WORKER_SA="storylab-sa@$PROJECT_ID.iam.gserviceaccount.com"
FRONTEND_PUBLIC_BASE_URL="${FRONTEND_PUBLIC_BASE_URL:-}"
RENDER_CANARY_DEPLOY="${RENDER_CANARY_DEPLOY:-true}"
RENDER_CANARY_TAG="${RENDER_CANARY_TAG:-canary}"

if [[ -z "$PROJECT_ID" ]]; then
  echo "ERROR: GOOGLE_CLOUD_PROJECT is not set and gcloud default project is not configured."
  echo "Run: gcloud config set project YOUR_PROJECT_ID"
  exit 1
fi

PROJECT_NUMBER="$(gcloud projects describe "$PROJECT_ID" --format='value(projectNumber)')"

if [[ -z "$PROJECT_NUMBER" ]]; then
  echo "ERROR: Could not resolve GCP project number for $PROJECT_ID."
  exit 1
fi

cloud_run_primary_url() {
  local service_name="$1"
  echo "https://${service_name}-${PROJECT_NUMBER}.${REGION}.run.app"
}

if [[ -z "$FRONTEND_PUBLIC_BASE_URL" ]]; then
  echo "ERROR: FRONTEND_PUBLIC_BASE_URL is required for editor export rendering."
  echo "Example: FRONTEND_PUBLIC_BASE_URL=https://your-frontend.example ./deploy.sh"
  exit 1
fi

echo ""
echo "════════════════════════════════════════════════════"
echo "  Content Factory — Cloud Run Deployment"
echo "  Project : $PROJECT_ID"
echo "  Region  : $REGION"
echo "  API     : $API_IMAGE"
echo "  Render  : $RENDER_IMAGE"
echo "════════════════════════════════════════════════════"
echo ""

# ── Enable required APIs ───────────────────────────────────────────────────────
echo "▶ Enabling required GCP APIs..."
gcloud services enable \
  run.googleapis.com \
  cloudbuild.googleapis.com \
  artifactregistry.googleapis.com \
  secretmanager.googleapis.com \
  firestore.googleapis.com \
  cloudtasks.googleapis.com \
  --project="$PROJECT_ID"

# ── Ensure Artifact Registry repo exists ──────────────────────────────────────
echo "▶ Ensuring Artifact Registry repository exists..."
gcloud artifacts repositories describe "$REPO" \
  --location="$REGION" \
  --project="$PROJECT_ID" &>/dev/null \
  || gcloud artifacts repositories create "$REPO" \
       --repository-format=docker \
       --location="$REGION" \
       --project="$PROJECT_ID" \
       --description="Content Factory container images"

# ── Ensure Cloud Tasks queue exists ───────────────────────────────────────────
echo "▶ Ensuring Cloud Tasks queue '$TASKS_QUEUE' exists..."
gcloud tasks queues describe "$TASKS_QUEUE" \
  --location="$REGION" \
  --project="$PROJECT_ID" &>/dev/null \
  || gcloud tasks queues create "$TASKS_QUEUE" \
       --location="$REGION" \
       --project="$PROJECT_ID" \
       --max-attempts=2 \
       --max-retry-duration=1800s \
       --max-concurrent-dispatches=5

# ── Ensure runtime service account can mint its own Cloud Tasks OIDC token ───
echo "▶ Ensuring $WORKER_SA can act as itself for Cloud Tasks OIDC..."
gcloud iam service-accounts add-iam-policy-binding "$WORKER_SA" \
  --project="$PROJECT_ID" \
  --member="serviceAccount:$WORKER_SA" \
  --role="roles/iam.serviceAccountUser" >/dev/null

# ── Ensure secrets exist in Secret Manager ────────────────────────────────────
echo "▶ Checking Secret Manager secrets..."
for SECRET in gemini-api-key sendgrid-api-key; do
  gcloud secrets describe "$SECRET" \
    --project="$PROJECT_ID" &>/dev/null \
  && echo "  ✓ $SECRET exists" \
  || echo "  ⚠ $SECRET does not exist — create it with:"
     echo "    gcloud secrets create $SECRET --replication-policy=automatic --project=$PROJECT_ID"
     echo "    echo 'YOUR_KEY' | gcloud secrets versions add $SECRET --data-file=- --project=$PROJECT_ID"
done

# ── Build & push API image ────────────────────────────────────────────────────
echo "▶ Building API image via Cloud Build..."
gcloud builds submit . \
  --config=backend/cloudbuild.yaml \
  --project="$PROJECT_ID" \
  --substitutions="_IMAGE=$API_IMAGE"

# ── Build & push render image ─────────────────────────────────────────────────
echo "▶ Building render image via Cloud Build..."
gcloud builds submit . \
  --config=timeline-render-worker/cloudbuild.yaml \
  --project="$PROJECT_ID" \
  --substitutions="_IMAGE=$RENDER_IMAGE"

EXISTING_API_URL="$(gcloud run services describe "$API_SERVICE" \
  --region="$REGION" \
  --project="$PROJECT_ID" \
  --format='value(status.url)' 2>/dev/null || true)"

deploy_worker_service() {
  local api_public_base_url="$1"

  gcloud run deploy "$WORKER_SERVICE" \
    --image="$API_IMAGE" \
    --region="$REGION" \
    --project="$PROJECT_ID" \
    --platform=managed \
    --no-allow-unauthenticated \
    --ingress=internal \
    --memory=2Gi \
    --cpu=1 \
    --timeout=900s \
    --concurrency=1 \
    --min-instances=0 \
    --max-instances=2 \
    --service-account="$WORKER_SA" \
    --set-env-vars="GCS_BUCKET=storylab-assets,GOOGLE_CLOUD_PROJECT=$PROJECT_ID,USE_VERTEX_AI=true,VERTEX_AI_LOCATION=$REGION,CLOUD_TASKS_QUEUE=$TASKS_QUEUE,CLOUD_TASKS_LOCATION=$REGION,TIMELINE_RENDER_WORKER_URL=$RENDER_URL,FRONTEND_PUBLIC_BASE_URL=$FRONTEND_PUBLIC_BASE_URL,API_PUBLIC_BASE_URL=$api_public_base_url" \
    --set-secrets="GEMINI_API_KEY=gemini-api-key:latest,SENDGRID_API_KEY=sendgrid-api-key:latest" \
    --no-cpu-throttling
}

wait_for_render_revision_ready() {
  local revision_name="$1"
  local max_checks=60
  local check=1

  echo "▶ Waiting for $RENDER_SERVICE revision $revision_name to become ready..."

  while (( check <= max_checks )); do
    local ready_status
    local ready_reason
    local ready_message

    ready_status="$(gcloud run revisions describe "$revision_name" \
      --region="$REGION" \
      --project="$PROJECT_ID" \
      --format='value(status.conditions[0].status)' 2>/dev/null || true)"
    ready_reason="$(gcloud run revisions describe "$revision_name" \
      --region="$REGION" \
      --project="$PROJECT_ID" \
      --format='value(status.conditions[0].reason)' 2>/dev/null || true)"
    ready_message="$(gcloud run revisions describe "$revision_name" \
      --region="$REGION" \
      --project="$PROJECT_ID" \
      --format='value(status.conditions[0].message)' 2>/dev/null || true)"

    if [[ "$ready_status" == "True" ]]; then
      echo "  ✓ $revision_name is ready"
      return 0
    fi

    if [[ "$ready_status" == "False" ]]; then
      echo "ERROR: $revision_name failed readiness ($ready_reason)"
      echo "$ready_message"
      return 1
    fi

    sleep 5
    ((check++))
  done

  echo "ERROR: Timed out waiting for $revision_name to become ready."
  return 1
}

verify_render_startup_log() {
  local revision_name="$1"
  local max_checks=12
  local check=1
  local sleep_seconds=5
  local logs_url="https://console.cloud.google.com/logs/viewer?project=$PROJECT_ID&resource=cloud_run_revision/service_name/$RENDER_SERVICE/revision_name/$revision_name"

  echo "▶ Verifying startup telemetry for revision $revision_name..."

  while (( check <= max_checks )); do
    local startup_log
    startup_log="$(gcloud logging read \
      "resource.type=\"cloud_run_revision\" AND resource.labels.service_name=\"$RENDER_SERVICE\" AND resource.labels.revision_name=\"$revision_name\" AND (textPayload:\"[RenderWorkerServer] listening\" OR jsonPayload.message:\"[RenderWorkerServer] listening\")" \
      --project="$PROJECT_ID" \
      --limit=1 \
      --format='value(timestamp)' 2>/dev/null || true)"

    if [[ -n "$startup_log" ]]; then
      echo "  ✓ Startup telemetry detected for $revision_name on attempt $check/$max_checks"
      return 0
    fi

    if (( check < max_checks )); then
      sleep "$sleep_seconds"
    fi
    ((check++))
  done

  echo "WARNING: Missing startup telemetry log for $revision_name after $max_checks attempts."
  echo "  Revision readiness already passed; continuing canary promotion without confirmed startup telemetry."
  echo "  Check logs: $logs_url"
  return 0
}

deploy_render_service() {
  echo "▶ Deploying $RENDER_SERVICE to Cloud Run..."

  local deploy_args=(
    run deploy "$RENDER_SERVICE"
    --image="$RENDER_IMAGE"
    --region="$REGION"
    --project="$PROJECT_ID"
    --platform=managed
    --no-allow-unauthenticated
    --ingress=all
    --memory=12Gi
    --cpu=4
    --timeout=900s
    --concurrency=1
    --min-instances=0
    --max-instances=2
    --service-account="$WORKER_SA"
    --set-env-vars="NODE_ENV=production,NODE_OPTIONS=--max-old-space-size=6144,PUPPETEER_EXECUTABLE_PATH=/usr/bin/chromium,FFMPEG_PATH=/usr/bin/ffmpeg,FFPROBE_PATH=/usr/bin/ffprobe"
    --no-cpu-throttling
  )

  if [[ "$RENDER_CANARY_DEPLOY" == "true" ]]; then
    deploy_args+=(--no-traffic --tag="$RENDER_CANARY_TAG")
  fi

  gcloud "${deploy_args[@]}"

  local created_revision
  created_revision="$(gcloud run services describe "$RENDER_SERVICE" \
    --region="$REGION" \
    --project="$PROJECT_ID" \
    --format='value(status.latestCreatedRevisionName)')"

  if [[ -z "$created_revision" ]]; then
    echo "ERROR: Could not determine latest created revision for $RENDER_SERVICE."
    return 1
  fi

  if [[ "$RENDER_CANARY_DEPLOY" == "true" ]]; then
    wait_for_render_revision_ready "$created_revision"
    verify_render_startup_log "$created_revision"
    echo "▶ Promoting $created_revision to 100% traffic..."
    gcloud run services update-traffic "$RENDER_SERVICE" \
      --region="$REGION" \
      --project="$PROJECT_ID" \
      --to-revisions="$created_revision=100" >/dev/null
    echo "  ✓ Promoted $created_revision"
  fi
}

# ── Deploy render service first ───────────────────────────────────────────────
# This service stays private by IAM/OIDC, but must use ingress=all so Cloud Run
# service-to-service requests over the run.app hostname can reach it.
deploy_render_service

RENDER_URL="$(cloud_run_primary_url "$RENDER_SERVICE")"

echo "  Render URL: $RENDER_URL"

echo "▶ Granting Cloud Run invoker access to $WORKER_SA on $RENDER_SERVICE..."
gcloud run services add-iam-policy-binding "$RENDER_SERVICE" \
  --region="$REGION" \
  --project="$PROJECT_ID" \
  --member="serviceAccount:$WORKER_SA" \
  --role="roles/run.invoker" >/dev/null

# ── Deploy worker first so we have its URL for the API service ────────────────
echo "▶ Deploying $WORKER_SERVICE to Cloud Run..."
BOOTSTRAP_API_URL="${EXISTING_API_URL:-https://placeholder.invalid}"
deploy_worker_service "$BOOTSTRAP_API_URL"

WORKER_URL="$(gcloud run services describe "$WORKER_SERVICE" \
  --region="$REGION" \
  --project="$PROJECT_ID" \
  --format='value(status.url)')"

echo "  Worker URL: $WORKER_URL"

# ── Deploy API service (lightweight, injects WORKER_URL) ──────────────────────
echo "▶ Deploying $API_SERVICE to Cloud Run..."
gcloud run deploy "$API_SERVICE" \
  --image="$API_IMAGE" \
  --region="$REGION" \
  --project="$PROJECT_ID" \
  --platform=managed \
  --allow-unauthenticated \
  --memory=512Mi \
  --cpu=1 \
  --timeout=60s \
  --concurrency=80 \
  --min-instances=0 \
  --max-instances=10 \
  --service-account="$WORKER_SA" \
  --set-env-vars="GCS_BUCKET=storylab-assets,GOOGLE_CLOUD_PROJECT=$PROJECT_ID,USE_VERTEX_AI=true,VERTEX_AI_LOCATION=$REGION,CLOUD_TASKS_QUEUE=$TASKS_QUEUE,CLOUD_TASKS_LOCATION=$REGION,WORKER_URL=$WORKER_URL,TIMELINE_RENDER_WORKER_URL=$RENDER_URL,YOUTUBE_CLIENT_SECRETS_FILE=/secrets/youtube_client_secrets.json" \
  --set-secrets="GEMINI_API_KEY=gemini-api-key:latest,/secrets/youtube_client_secrets.json=youtube-client-secrets:latest" \
  --no-cpu-throttling

# ── Print result ──────────────────────────────────────────────────────────────
API_URL="$(gcloud run services describe "$API_SERVICE" \
  --region="$REGION" \
  --project="$PROJECT_ID" \
  --format='value(status.url)')"

# ── Re-deploy worker with the final public API URL used for export media normalization ──
echo "▶ Updating $WORKER_SERVICE with final export normalization URLs..."
deploy_worker_service "$API_URL"

echo ""
echo "════════════════════════════════════════════════════"
echo "  Deployment complete!"
echo ""
echo "  API Service  : $API_URL"
echo "  Worker URL   : $WORKER_URL"
echo "  Render URL   : $RENDER_URL"
echo ""
echo "  Health check : $API_URL/health"
echo "  API docs     : $API_URL/docs"
echo "  Tasks queue  : https://console.cloud.google.com/cloudtasks/queue/$REGION/$TASKS_QUEUE/tasks?project=$PROJECT_ID"
echo "════════════════════════════════════════════════════"
echo ""
echo "To view logs:"
echo "  API    : gcloud run services logs read $API_SERVICE --region=$REGION --project=$PROJECT_ID"
echo "  Worker : gcloud run services logs read $WORKER_SERVICE --region=$REGION --project=$PROJECT_ID"
echo "  Render : gcloud run services logs read $RENDER_SERVICE --region=$REGION --project=$PROJECT_ID"
