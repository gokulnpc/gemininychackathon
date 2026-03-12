#!/bin/bash
# =============================================================================
# deploy-render.sh — Render-only Cloud Run deploy (build + canary + promote)
#
# Usage:
#   ./deploy-render.sh
#   REGION=us-central1 ./deploy-render.sh
#   GOOGLE_CLOUD_PROJECT=my-proj ./deploy-render.sh
#   RENDER_CANARY_DEPLOY=false ./deploy-render.sh
# =============================================================================

set -euo pipefail

PROJECT_ID="${GOOGLE_CLOUD_PROJECT:-$(gcloud config get-value project 2>/dev/null)}"
REGION="${REGION:-us-central1}"
RENDER_SERVICE="voicevid-render"
REPO="voicevid"
SHORT_SHA="$(git rev-parse --short HEAD 2>/dev/null || echo 'latest')"
RENDER_IMAGE="$REGION-docker.pkg.dev/$PROJECT_ID/$REPO/render:$SHORT_SHA"
WORKER_SA="storylab-sa@$PROJECT_ID.iam.gserviceaccount.com"
RENDER_CANARY_DEPLOY="${RENDER_CANARY_DEPLOY:-true}"
RENDER_CANARY_TAG="${RENDER_CANARY_TAG:-canary}"
RENDER_CANARY_LOG_GATING="${RENDER_CANARY_LOG_GATING:-best-effort}"

if [[ -z "$PROJECT_ID" ]]; then
  echo "ERROR: GOOGLE_CLOUD_PROJECT is not set and gcloud default project is not configured."
  echo "Run: gcloud config set project YOUR_PROJECT_ID"
  exit 1
fi

echo ""
echo "════════════════════════════════════════════════════"
echo "  Render-Only Cloud Run Deployment"
echo "  Project : $PROJECT_ID"
echo "  Region  : $REGION"
echo "  Image   : $RENDER_IMAGE"
echo "  Canary  : $RENDER_CANARY_DEPLOY"
echo "  Log gate: $RENDER_CANARY_LOG_GATING"
echo "════════════════════════════════════════════════════"
echo ""

echo "▶ Enabling required GCP APIs..."
gcloud services enable \
  run.googleapis.com \
  cloudbuild.googleapis.com \
  artifactregistry.googleapis.com \
  --project="$PROJECT_ID"

echo "▶ Ensuring Artifact Registry repository exists..."
gcloud artifacts repositories describe "$REPO" \
  --location="$REGION" \
  --project="$PROJECT_ID" &>/dev/null \
  || gcloud artifacts repositories create "$REPO" \
       --repository-format=docker \
       --location="$REGION" \
       --project="$PROJECT_ID" \
       --description="Content Factory container images"

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
  local startup_log=""
  local attempts=12
  local attempt=1

  echo "▶ Verifying startup telemetry for revision $revision_name..."

  while (( attempt <= attempts )); do
    startup_log="$(gcloud logging read \
      "resource.type=\"cloud_run_revision\" AND resource.labels.service_name=\"$RENDER_SERVICE\" AND resource.labels.revision_name=\"$revision_name\" AND logName=\"projects/$PROJECT_ID/logs/run.googleapis.com%2Fstdout\" AND textPayload:\"[RenderWorkerServer] listening\"" \
      --project="$PROJECT_ID" \
      --limit=1 \
      --format='value(textPayload)' 2>/dev/null || true)"

    if [[ -n "$startup_log" ]]; then
      break
    fi

    sleep 5
    ((attempt++))
  done

  if [[ -n "$startup_log" ]]; then
    echo "  ✓ Startup telemetry detected for $revision_name"
    return 0
  fi

  local logs_url="https://console.cloud.google.com/logs/viewer?project=$PROJECT_ID&resource=cloud_run_revision/service_name/$RENDER_SERVICE/revision_name/$revision_name"
  if [[ "$RENDER_CANARY_LOG_GATING" == "strict" ]]; then
    echo "ERROR: Missing startup telemetry log for $revision_name."
    echo "Check logs: $logs_url"
    return 1
  fi

  echo "⚠ Startup telemetry log not observed yet for $revision_name."
  echo "  Continuing because RENDER_CANARY_LOG_GATING=$RENDER_CANARY_LOG_GATING"
  echo "  Logs: $logs_url"
  return 0
}

echo "▶ Building render image via Cloud Build..."
gcloud builds submit . \
  --config=timeline-render-worker/cloudbuild.yaml \
  --project="$PROJECT_ID" \
  --substitutions="_IMAGE=$RENDER_IMAGE"

echo "▶ Deploying $RENDER_SERVICE..."
deploy_args=(
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

created_revision="$(gcloud run services describe "$RENDER_SERVICE" \
  --region="$REGION" \
  --project="$PROJECT_ID" \
  --format='value(status.latestCreatedRevisionName)')"

if [[ -z "$created_revision" ]]; then
  echo "ERROR: Could not determine latest created revision for $RENDER_SERVICE."
  exit 1
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

RENDER_URL="$(gcloud run services describe "$RENDER_SERVICE" \
  --region="$REGION" \
  --project="$PROJECT_ID" \
  --format='value(status.url)')"
READY_REVISION="$(gcloud run services describe "$RENDER_SERVICE" \
  --region="$REGION" \
  --project="$PROJECT_ID" \
  --format='value(status.latestReadyRevisionName)')"

echo ""
echo "════════════════════════════════════════════════════"
echo "  Render deployment complete"
echo "  Service URL     : $RENDER_URL"
echo "  Created revision: $created_revision"
echo "  Ready revision  : $READY_REVISION"
echo "════════════════════════════════════════════════════"
echo ""
echo "To view logs:"
echo "  gcloud run services logs read $RENDER_SERVICE --region=$REGION --project=$PROJECT_ID"
