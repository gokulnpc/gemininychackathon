# ── Stage 1: build ────────────────────────────────────────────────────────────
FROM node:20-bookworm-slim AS builder

RUN corepack enable pnpm

WORKDIR /app

# Install dependencies first (cached layer)
COPY package.json pnpm-lock.yaml ./
RUN pnpm install --no-frozen-lockfile

# NEXT_PUBLIC_* vars must be available at build time — Next.js bakes them
# into the JS bundle. Defaults point to the local Docker setup.
ARG NEXT_PUBLIC_API_URL=http://localhost:8000
ARG NEXT_PUBLIC_FIREBASE_API_KEY
ARG NEXT_PUBLIC_FIREBASE_AUTH_DOMAIN
ARG NEXT_PUBLIC_FIREBASE_PROJECT_ID
ARG NEXT_PUBLIC_FIREBASE_STORAGE_BUCKET
ARG NEXT_PUBLIC_FIREBASE_MESSAGING_SENDER_ID
ARG NEXT_PUBLIC_FIREBASE_APP_ID

ENV NEXT_PUBLIC_API_URL=$NEXT_PUBLIC_API_URL \
    NEXT_PUBLIC_FIREBASE_API_KEY=$NEXT_PUBLIC_FIREBASE_API_KEY \
    NEXT_PUBLIC_FIREBASE_AUTH_DOMAIN=$NEXT_PUBLIC_FIREBASE_AUTH_DOMAIN \
    NEXT_PUBLIC_FIREBASE_PROJECT_ID=$NEXT_PUBLIC_FIREBASE_PROJECT_ID \
    NEXT_PUBLIC_FIREBASE_STORAGE_BUCKET=$NEXT_PUBLIC_FIREBASE_STORAGE_BUCKET \
    NEXT_PUBLIC_FIREBASE_MESSAGING_SENDER_ID=$NEXT_PUBLIC_FIREBASE_MESSAGING_SENDER_ID \
    NEXT_PUBLIC_FIREBASE_APP_ID=$NEXT_PUBLIC_FIREBASE_APP_ID

# Copy source and build
# prebuild hook (copy-browser-render-assets.mjs) runs automatically,
# copying FFmpeg WASM + Twick public assets into public/ before Next.js processes them.
COPY . .
RUN pnpm build


# ── Stage 2: runtime ──────────────────────────────────────────────────────────
FROM node:20-bookworm-slim

WORKDIR /app

# Standalone output includes only required node_modules
COPY --from=builder /app/.next/standalone ./
COPY --from=builder /app/.next/static ./.next/static
COPY --from=builder /app/public ./public

EXPOSE 3000

ENV PORT=3000 \
    HOSTNAME=0.0.0.0

HEALTHCHECK --interval=30s --timeout=10s --start-period=20s --retries=3 \
    CMD node -e "fetch('http://localhost:3000').then(r => { if(!r.ok) process.exit(1) }).catch(() => process.exit(1))"

CMD ["node", "server.js"]
