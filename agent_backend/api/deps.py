from fastapi import Request, HTTPException
from agent_backend.auth.jwt_handler import get_user_id_from_token, current_jwt
from jose import JWTError


async def get_current_user_id(request: Request) -> str:
    """FastAPI dependency: extract userId from Authorization header.

    Also stores the raw JWT in a ContextVar so downstream tools can forward
    it to the Spring Boot backend.
    """
    auth_header = request.headers.get("Authorization")
    if not auth_header:
        raise HTTPException(status_code=401, detail="Missing Authorization header")
    if not auth_header.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Authorization header must use Bearer scheme")

    token = auth_header[7:]
    if not token:
        raise HTTPException(status_code=401, detail="Empty token")

    try:
        user_id = get_user_id_from_token(token)
        current_jwt.set(token)
        return user_id
    except JWTError as e:
        raise HTTPException(status_code=401, detail=f"Invalid or expired token: {str(e)}")
    except Exception:
        raise HTTPException(status_code=401, detail="Token validation failed")
