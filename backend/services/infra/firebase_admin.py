import os

import firebase_admin
from firebase_admin import auth, credentials

# Initialise once — reuse ADC (Application Default Credentials) on GCP/Cloud Run.
# Locally, set GOOGLE_APPLICATION_CREDENTIALS to a service-account JSON file.
if not firebase_admin._apps:
    project_id = os.environ.get("GOOGLE_CLOUD_PROJECT", "story-labs-factory")
    firebase_admin.initialize_app(
        credentials.ApplicationDefault(),
        options={"projectId": project_id},
    )


def verify_id_token(token: str) -> dict:
    """Verify a Firebase ID token and return the decoded claims."""
    return auth.verify_id_token(token)
