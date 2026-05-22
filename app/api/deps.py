from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from beanie import PydanticObjectId
from app.core.security import decode_token
from app.models.developer import Developer

security = HTTPBearer()


async def get_current_developer(
    credentials: HTTPAuthorizationCredentials = Depends(security),
) -> Developer:
    """
    Dependency to get current authenticated developer.
    Validates JWT token and returns Developer object.
    """
    token = credentials.credentials
    payload = decode_token(token)

    if not payload or payload.get("type") != "access":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )

    developer_id = payload.get("sub")
    if not developer_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token payload",
        )

    # Query MongoDB with Beanie
    developer = await Developer.get(PydanticObjectId(developer_id))
    if not developer:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Developer not found",
        )

    if not developer.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Developer account is inactive",
        )

    return developer


async def get_current_active_developer(
    current_developer: Developer = Depends(get_current_developer)
) -> Developer:
    """
    Dependency to ensure developer is active.
    """
    if not current_developer.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Inactive developer account"
        )
    return current_developer
