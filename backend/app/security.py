import logging
from fastapi import Header, HTTPException, status, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from itsdangerous import URLSafeTimedSerializer, SignatureExpired, BadSignature
from app.config import API_KEY

logger = logging.getLogger(__name__)

# Serializer for token signing
serializer = URLSafeTimedSerializer(API_KEY)

security_bearer = HTTPBearer(auto_error=False)

def create_access_token(username: str, role: str, tenant_id: str) -> str:
    return serializer.dumps({"username": username, "role": role, "tenant_id": tenant_id})


def decode_access_token(token: str) -> dict:
    try:
        # Token is valid for 1 day
        data = serializer.loads(token, max_age=86400)
        return data
    except SignatureExpired:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token has expired",
        )
    except BadSignature:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid signature on token",
        )

async def check_api_key(x_api_key: str | None = Header(default=None, alias="X-Api-Key")):
    if x_api_key != API_KEY:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing API key",
        )

async def get_current_user(credentials: HTTPAuthorizationCredentials | None = Depends(security_bearer)) -> dict:
    if not credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing Authorization header",
        )
    token = credentials.credentials
    return decode_access_token(token)

def require_role(allowed_roles: list[str]):
    async def dependency(user: dict = Depends(get_current_user)) -> dict:
        role = user.get("role")
        if role not in allowed_roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Action requires one of roles: {allowed_roles}",
            )
        return user
    return dependency

