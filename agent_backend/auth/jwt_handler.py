from contextvars import ContextVar
from jose import jwt, JWTError
from agent_backend.config import settings

ACCEPTED_ALGORITHMS = ["HS256", "HS384", "HS512"]

# Propagate the raw JWT from the API layer to downstream tools
# so they can forward it to the Spring Boot backend.
current_jwt: ContextVar[str] = ContextVar("current_jwt", default="")


def verify_token(token: str) -> dict:
    """Verify JWT and return payload. Raises JWTError on failure.

    Validates signature, algorithm, and standard claims (exp, iat).
    """
    payload = jwt.decode(
        token,
        settings.jwt_secret,
        algorithms=ACCEPTED_ALGORITHMS,
        options={
            "verify_exp": True,
            "verify_iat": True,
        },
    )
    return payload


def get_user_id_from_token(token: str) -> str:
    """Extract userId (sub claim) from a verified JWT."""
    payload = verify_token(token)
    sub = payload.get("sub")
    if not sub:
        raise JWTError("Token missing 'sub' claim")
    return sub
