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
REPO="voicevid"
SHORT_SHA="$(git rev-parse --short HEAD 2>/dev/null || echo 'latest')"
IMAGE="$REGION-docker.pkg.dev/$PROJECT_ID/$REPO/api:$SHORT_SHA"
TASKS_QUEUE="video-generation"
WORKER_SA="storylab-sa@$PROJECT_ID.iam.gserviceaccount.com"

if [[ -z "$PROJECT_ID" ]]; then
  echo "ERROR: GOOGLE_CLOUD_PROJECT is not set and gcloud default project is not configured."
  echo "Run: gcloud config set project YOUR_PROJECT_ID"
  exit 1
fi

echo ""
echo "════════════════════════════════════════════════════"
echo "  Content Factory — Cloud Run Deployment"
echo "  Project : $PROJECT_ID"
echo "  Region  : $REGION"
echo "  Image   : $IMAGE"
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

# ── Build & push image ────────────────────────────────────────────────────────
echo "▶ Building Docker image via Cloud Build..."
gcloud builds submit . \
  --config=backend/cloudbuild.yaml \
  --project="$PROJECT_ID" \
  --substitutions="_IMAGE=$IMAGE"

# ── Deploy Worker service first (so we have its URL for the API service) ──────
echo "▶ Deploying $WORKER_SERVICE to Cloud Run..."
gcloud run deploy "$WORKER_SERVICE" \
  --image="$IMAGE" \
  --region="$REGION" \
  --project="$PROJECT_ID" \
  --platform=managed \
  --no-allow-unauthenticated \
  --ingress=internal \
  --memory=4Gi \
  --cpu=4 \
  --timeout=900s \
  --concurrency=1 \
  --min-instances=0 \
  --max-instances=5 \
  --service-account="$WORKER_SA" \
  --set-env-vars="GCS_BUCKET=storylab-assets,GOOGLE_CLOUD_PROJECT=$PROJECT_ID,USE_VERTEX_AI=true,VERTEX_AI_LOCATION=$REGION,CLOUD_TASKS_QUEUE=$TASKS_QUEUE,CLOUD_TASKS_LOCATION=$REGION" \
  --set-secrets="GEMINI_API_KEY=gemini-api-key:latest,SENDGRID_API_KEY=sendgrid-api-key:latest" \
  --no-cpu-throttling

WORKER_URL="$(gcloud run services describe "$WORKER_SERVICE" \
  --region="$REGION" \
  --project="$PROJECT_ID" \
  --format='value(status.url)')"

echo "  Worker URL: $WORKER_URL"

# ── Deploy API service (lightweight, injects WORKER_URL) ──────────────────────
echo "▶ Deploying $API_SERVICE to Cloud Run..."
gcloud run deploy "$API_SERVICE" \
  --image="$IMAGE" \
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
  --set-env-vars="GCS_BUCKET=storylab-assets,GOOGLE_CLOUD_PROJECT=$PROJECT_ID,USE_VERTEX_AI=true,VERTEX_AI_LOCATION=$REGION,CLOUD_TASKS_QUEUE=$TASKS_QUEUE,CLOUD_TASKS_LOCATION=$REGION,WORKER_URL=$WORKER_URL,YOUTUBE_CLIENT_SECRETS_FILE=/secrets/youtube_client_secrets.json" \
  --set-secrets="GEMINI_API_KEY=gemini-api-key:latest,/secrets/youtube_client_secrets.json=youtube-client-secrets:latest" \
  --no-cpu-throttling

# ── Print result ──────────────────────────────────────────────────────────────
API_URL="$(gcloud run services describe "$API_SERVICE" \
  --region="$REGION" \
  --project="$PROJECT_ID" \
  --format='value(status.url)')"

echo ""
echo "════════════════════════════════════════════════════"
echo "  Deployment complete!"
echo ""
echo "  API Service  : $API_URL"
echo "  Worker URL   : $WORKER_URL"
echo ""
echo "  Health check : $API_URL/health"
echo "  API docs     : $API_URL/docs"
echo "  Tasks queue  : https://console.cloud.google.com/cloudtasks/queue/$REGION/$TASKS_QUEUE/tasks?project=$PROJECT_ID"
echo "════════════════════════════════════════════════════"
echo ""
echo "To view logs:"
echo "  API    : gcloud run services logs read $API_SERVICE --region=$REGION --project=$PROJECT_ID"
echo "  Worker : gcloud run services logs read $WORKER_SERVICE --region=$REGION --project=$PROJECT_ID"
