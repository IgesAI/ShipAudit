import base64
import hashlib
import hmac
import secrets
from datetime import UTC, datetime, timedelta

from jose import jwt

from app.core.config import settings

ALGORITHM = "HS256"
HASH_ALGORITHM = "pbkdf2_sha256"
HASH_ITERATIONS = 390_000


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, HASH_ITERATIONS)
    return "$".join(
        [
            HASH_ALGORITHM,
            str(HASH_ITERATIONS),
            base64.urlsafe_b64encode(salt).decode("ascii"),
            base64.urlsafe_b64encode(digest).decode("ascii"),
        ]
    )


def verify_password(password: str, password_hash: str) -> bool:
    try:
        algorithm, iterations, salt_b64, digest_b64 = password_hash.split("$", 3)
    except ValueError:
        return False
    if algorithm != HASH_ALGORITHM:
        return False
    salt = base64.urlsafe_b64decode(salt_b64.encode("ascii"))
    expected = base64.urlsafe_b64decode(digest_b64.encode("ascii"))
    actual = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, int(iterations))
    return hmac.compare_digest(actual, expected)


def create_access_token(subject: str, scopes: list[str] | None = None) -> str:
    expires = datetime.now(UTC) + timedelta(minutes=settings.access_token_minutes)
    payload = {"sub": subject, "exp": expires, "scopes": scopes or []}
    return jwt.encode(payload, settings.secret_key, algorithm=ALGORITHM)
