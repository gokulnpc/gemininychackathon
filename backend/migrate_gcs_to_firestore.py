"""One-time migration: read project metadata.json files from GCS → write to Firestore.

Run from backend/:
    python migrate_gcs_to_firestore.py
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import sys

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger(__name__)

# Ensure backend/ is on the path
sys.path.insert(0, os.path.dirname(__file__))


async def migrate():
    from config import get_settings
    from services import gcs
    from google.cloud import firestore

    settings = get_settings()
    if not settings.google_cloud_project:
        logger.error("GOOGLE_CLOUD_PROJECT not set — cannot write to Firestore")
        return

    logger.info("Project: %s | Bucket: %s", settings.google_cloud_project, settings.gcs_bucket)

    # List all metadata.json keys in GCS
    all_keys = await gcs.list_keys("projects/")
    meta_keys = [
        k for k in all_keys
        if k.endswith("/metadata.json") and len(k.split("/")) == 3
    ]
    logger.info("Found %d metadata files in GCS", len(meta_keys))

    db = firestore.Client(project=settings.google_cloud_project)

    migrated = 0
    for key in meta_keys:
        project_id = key.split("/")[1]
        try:
            data = await gcs.load_json(key)
            if not data:
                logger.warning("Empty metadata for %s, skipping", project_id)
                continue

            # Check if already in Firestore
            doc = db.collection("projects").document(project_id).get()
            if doc.exists:
                logger.info("Already in Firestore: %s — skipping", project_id)
                continue

            db.collection("projects").document(project_id).set(data)
            hook = data.get("hook", {})
            hook_text = hook.get("text", "?") if isinstance(hook, dict) else str(hook)[:60]
            logger.info("Migrated %s → %s", project_id, hook_text[:60])
            migrated += 1
        except Exception as e:
            logger.error("Failed %s: %s", project_id, e)

    logger.info("Done. Migrated %d / %d projects to Firestore.", migrated, len(meta_keys))


if __name__ == "__main__":
    asyncio.run(migrate())
