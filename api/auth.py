import hmac
import json
import os

from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer


_bearer = HTTPBearer(auto_error=False)


def organization_keys():
    try:
        organizations = json.loads(os.environ.get("API_KEYS_JSON", "{}"))
    except json.JSONDecodeError as error:
        raise RuntimeError("API_KEYS_JSON must be valid JSON") from error
    if not isinstance(organizations, dict):
        raise RuntimeError("API_KEYS_JSON must map organization IDs to keys")
    if not organizations and os.environ.get("APP_ENV") == "production":
        raise RuntimeError("API_KEYS_JSON must contain at least one organization key in production")
    for organization_id, token in organizations.items():
        if not isinstance(organization_id, str) or not organization_id or len(organization_id) > 128:
            raise RuntimeError("API_KEYS_JSON contains an invalid organization ID")
        if not isinstance(token, str) or not token:
            raise RuntimeError("API_KEYS_JSON contains an invalid API key")
        if os.environ.get("APP_ENV") == "production" and len(token) < 32:
            raise RuntimeError("Production API keys must contain at least 32 characters")
    return organizations


def current_organization(credentials: HTTPAuthorizationCredentials = Depends(_bearer)):
    if credentials is None:
        raise HTTPException(status_code=401, detail="Bearer API key required")
    organizations = organization_keys()
    if not organizations and os.environ.get("APP_ENV") != "production":
        organizations = {"local-development": "local-dev-key"}
    for organization_id, token in organizations.items():
        if isinstance(token, str) and hmac.compare_digest(credentials.credentials, token):
            return organization_id
    raise HTTPException(status_code=401, detail="Invalid API key")
