from fastapi import APIRouter, Depends, HTTPException, status
from app.schemas.auth import SignupRequest, LoginRequest, TokenResponse, DeveloperResponse
from app.models.developer import Developer
from app.core.security import verify_password, get_password_hash, create_access_token, create_refresh_token
from app.api.deps import get_current_developer

router = APIRouter()


@router.post("/signup", response_model=TokenResponse, status_code=status.HTTP_201_CREATED)
async def signup(request: SignupRequest):
    """
    Register a new developer account.
    Returns access and refresh tokens.
    """
    # Check if email already exists
    existing_developer = await Developer.find_one(Developer.email == request.email)
    if existing_developer:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email already registered"
        )

    # Create new developer
    hashed_password = get_password_hash(request.password)
    new_developer = Developer(
        email=request.email,
        hashed_password=hashed_password,
        first_name=request.first_name,
        last_name=request.last_name,
        company_name=request.company_name,
    )

    await new_developer.insert()

    # Generate tokens
    access_token = create_access_token(data={"sub": str(new_developer.id)})
    refresh_token = create_refresh_token(data={"sub": str(new_developer.id)})

    return TokenResponse(
        access_token=access_token,
        refresh_token=refresh_token
    )


@router.post("/login", response_model=TokenResponse)
async def login(request: LoginRequest):
    """
    Login with email and password.
    Returns access and refresh tokens.
    """
    developer = await Developer.find_one(Developer.email == request.email)

    if not developer or not verify_password(request.password, developer.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if not developer.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Account is inactive"
        )

    # Generate tokens
    access_token = create_access_token(data={"sub": str(developer.id)})
    refresh_token = create_refresh_token(data={"sub": str(developer.id)})

    return TokenResponse(
        access_token=access_token,
        refresh_token=refresh_token
    )


@router.get("/me", response_model=DeveloperResponse)
async def get_current_user(current_developer: Developer = Depends(get_current_developer)):
    """
    Get current authenticated developer info.
    Protected route - requires valid JWT token.
    """
    return current_developer


@router.post("/logout")
async def logout():
    """
    Logout (client-side token removal).
    Backend is stateless with JWT.
    """
    return {"message": "Successfully logged out"}
