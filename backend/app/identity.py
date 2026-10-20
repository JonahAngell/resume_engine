import logging
import os
from dataclasses import dataclass
from urllib.parse import urlparse

import httpx
from fastapi import Header, HTTPException, Request, status


@dataclass(frozen=True)
class CurrentUser:
    external_id: str
    username: str
    display_name: str
    email: str | None


logger = logging.getLogger("resume_engine.identity")
LOCAL_DB_HOSTS = {"localhost", "127.0.0.1", "::1", "db", "postgres"}


def local_auth_enabled() -> bool:
    return os.getenv("APP_ENV", "").strip().lower() == "local"


def _database_host() -> str:
    value = (
        os.getenv("STUDIOSHARE_DB_URL", "").strip()
        or os.getenv("DATABASE_URL", "").strip()
    )
    return (urlparse(value).hostname or "").lower() if value else ""


def check_local_auth_safety() -> None:
    """Refuse to run unauthenticated against a database that is not a local one."""
    if not local_auth_enabled():
        return
    host = _database_host()
    if host and host not in LOCAL_DB_HOSTS:
        raise RuntimeError(
            "APP_ENV=local disables authentication but the database host is not local. "
            "Unset APP_ENV or point DATABASE_URL at a local database."
        )
    logger.warning("APP_ENV=local: authentication is disabled; every request is the development user.")


def _local_user() -> CurrentUser | None:
    if not local_auth_enabled():
        return None
    if _database_host() not in LOCAL_DB_HOSTS and _database_host():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Local development identity is not allowed with this database.",
        )
    external_id = os.getenv("DEV_USER_ID", "local-user").strip()
    username = os.getenv("DEV_USERNAME", "local.user").strip()
    if not external_id or not username:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Local development identity is incomplete.",
        )
    return CurrentUser(
        external_id=external_id,
        username=username,
        display_name=os.getenv("DEV_DISPLAY_NAME", "Local User").strip() or username,
        email=os.getenv("DEV_EMAIL", "").strip() or None,
    )


def _bearer_fallback_enabled() -> bool:
    return os.getenv("ALLOW_BEARER_AUTH", "").strip().lower() == "true"


async def _studioshare_user(access_token: str) -> CurrentUser:
    api_url = os.getenv("STUDIOSHARE_API_URL", "").strip().rstrip("/")
    if not api_url:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="StudioShare user service is not configured.",
        )
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(
                f"{api_url}/me",
                headers={
                    "Authorization": f"Bearer {access_token}",
                    "Accept": "application/json",
                },
            )
    except httpx.HTTPError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="StudioShare user service is unavailable.",
        ) from exc
    if response.status_code in {
        status.HTTP_401_UNAUTHORIZED,
        status.HTTP_403_FORBIDDEN,
    }:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="StudioShare login is no longer valid. Sign in again.",
        )
    if not response.is_success:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="StudioShare user lookup failed.",
        )
    try:
        user = response.json()
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="StudioShare returned an invalid user response.",
        ) from exc
    if not isinstance(user, dict):
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="StudioShare returned an invalid user response.",
        )
    external_id = str(user.get("id") or "").strip()
    username = str(user.get("username") or "").strip()
    display_name = str(user.get("fullName") or username).strip()
    email = str(user.get("email") or "").strip() or None
    if not external_id or not username:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="StudioShare user response is missing required identity fields.",
        )
    return CurrentUser(external_id, username, display_name, email)


async def resolve_current_user(
    request: Request,
    authorization: str | None = Header(default=None),
) -> CurrentUser:
    local_user = _local_user()
    if local_user is not None:
        return local_user
    access_token = request.cookies.get("access_token", "").strip()
    if not access_token and authorization and _bearer_fallback_enabled():
        scheme, separator, credential = authorization.partition(" ")
        if separator and scheme.lower() == "bearer":
            access_token = credential.strip()
    if not access_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authenticated StudioShare identity is required.",
        )
    return await _studioshare_user(access_token)
