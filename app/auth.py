from dataclasses import dataclass
from functools import lru_cache

import jwt
from fastapi import Header, HTTPException

from app.config import auth_required, supabase_jwks_url, supabase_url


@dataclass
class CurrentUser:
    id: str
    email: str | None = None


def _issuer():
    base_url = supabase_url().rstrip("/")
    return f"{base_url}/auth/v1"


@lru_cache(maxsize=1)
def _jwks_client():
    jwks_url = supabase_jwks_url()
    if not jwks_url:
        raise HTTPException(status_code=500, detail="SUPABASE_JWKS_URL is not configured.")
    return jwt.PyJWKClient(jwks_url)


def _extract_bearer_token(authorization: str | None):
    if not authorization:
        raise HTTPException(status_code=401, detail="Missing bearer token")

    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not token.strip():
        raise HTTPException(status_code=401, detail="Invalid authorization header")
    return token.strip()


def require_user(authorization: str | None = Header(default=None)):
    if not auth_required():
        return CurrentUser(id="local-dev-user", email="local@example.com")

    token = _extract_bearer_token(authorization)

    try:
        signing_key = _jwks_client().get_signing_key_from_jwt(token)
        claims = jwt.decode(
            token,
            signing_key.key,
            algorithms=["RS256", "ES256"],
            issuer=_issuer(),
            audience="authenticated",
        )
    except jwt.InvalidTokenError as exc:
        raise HTTPException(status_code=401, detail=f"Invalid token: {exc}") from exc
    except Exception as exc:
        raise HTTPException(status_code=401, detail=f"Token verification failed: {exc}") from exc

    subject = claims.get("sub")
    if not subject:
        raise HTTPException(status_code=401, detail="Token is missing subject claim")

    return CurrentUser(id=subject, email=claims.get("email"))
