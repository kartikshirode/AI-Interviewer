import bcrypt
from jose import JWTError, jwt
from datetime import datetime, timedelta, timezone
from typing import Optional
from app.core.config import settings


# Stable dummy hash used to make login timing roughly constant when an account
# does not exist. Computed lazily so importing this module is cheap.
_DUMMY_PASSWORD_HASH: Optional[str] = None


def _dummy_hash() -> str:
    global _DUMMY_PASSWORD_HASH
    if _DUMMY_PASSWORD_HASH is None:
        _DUMMY_PASSWORD_HASH = bcrypt.hashpw(
            b"dummy-password-for-timing", bcrypt.gensalt()
        ).decode("utf-8")
    return _DUMMY_PASSWORD_HASH


def verify_password(plain_password: str, hashed_password: str) -> bool:
    try:
        return bcrypt.checkpw(
            plain_password.encode("utf-8"), hashed_password.encode("utf-8")
        )
    except (ValueError, TypeError):
        return False


def dummy_verify_password(plain_password: str) -> None:
    """Run a bcrypt check against a fixed dummy hash to equalize timing for
    authentication failures where the user does not exist."""
    try:
        bcrypt.checkpw(
            plain_password.encode("utf-8"), _dummy_hash().encode("utf-8")
        )
    except Exception:
        pass


def get_password_hash(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + (
        expires_delta or timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    )
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, settings.SECRET_KEY, algorithm=settings.ALGORITHM)


def decode_token(token: str) -> Optional[dict]:
    try:
        return jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
    except JWTError:
        return None


def create_candidate_token(candidate_id: int, interview_id: int, ttl_minutes: int = 240) -> str:
    """Issue a session token for a candidate that is bound to a specific
    interview. Used to authenticate the unauthenticated candidate flow."""
    expire = datetime.now(timezone.utc) + timedelta(minutes=ttl_minutes)
    payload = {
        "sub": f"candidate:{candidate_id}",
        "candidate_id": candidate_id,
        "interview_id": interview_id,
        "scope": "candidate",
        "exp": expire,
    }
    return jwt.encode(payload, settings.SECRET_KEY, algorithm=settings.ALGORITHM)


def decode_candidate_token(token: str) -> Optional[dict]:
    payload = decode_token(token)
    if not payload or payload.get("scope") != "candidate":
        return None
    return payload
