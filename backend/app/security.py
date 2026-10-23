import uuid
from datetime import timedelta

import bcrypt
import jwt

from app.config import get_settings
from app.models import utcnow

COOKIE_NAME = "cs_session"


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode()[:72], bcrypt.gensalt()).decode()


def verify_password(password: str, password_hash: str | None) -> bool:
    if not password_hash:
        return False
    return bcrypt.checkpw(password.encode()[:72], password_hash.encode())


def issue_token(user_id: uuid.UUID, org_id: uuid.UUID, role: str) -> str:
    s = get_settings()
    now = utcnow()
    payload = {"sub": str(user_id), "org": str(org_id), "role": role, "iat": now,
               "exp": now + timedelta(hours=s.jwt_ttl_hours)}
    return jwt.encode(payload, s.jwt_secret, algorithm="HS256")


def decode_token(token: str) -> dict | None:
    try:
        return jwt.decode(token, get_settings().jwt_secret, algorithms=["HS256"])
    except jwt.PyJWTError:
        return None


def set_session_cookie(response, token: str) -> None:
    s = get_settings()
    response.set_cookie(COOKIE_NAME, token, httponly=True, secure=s.cookie_secure, samesite=s.cookie_samesite,
                        max_age=s.jwt_ttl_hours * 3600, path="/")
