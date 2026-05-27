from fastapi import APIRouter, Depends, HTTPException, status, Response, Request
from fastapi.responses import RedirectResponse
from app.schemas.auth import (
    SignupRequest, LoginRequest, TokenResponse, DeveloperResponse,
    VerifyEmailRequest, ResendVerificationRequest,
    ForgotPasswordRequest, ResetPasswordRequest, ChangePasswordRequest
)
from app.models.developer import Developer
from app.core.security import verify_password, get_password_hash, create_access_token, create_refresh_token
from app.api.deps import get_current_developer
from app.services.email_service import email_service
from app.core.config import settings
from datetime import datetime, timedelta
from authlib.integrations.starlette_client import OAuth
from itsdangerous import URLSafeTimedSerializer
import random
import string
import httpx

router = APIRouter()

# Cookie settings
COOKIE_ACCESS_TOKEN_NAME = "access_token"
COOKIE_REFRESH_TOKEN_NAME = "refresh_token"
COOKIE_MAX_AGE = 7 * 24 * 60 * 60  # 7 days
COOKIE_DOMAIN = None  # Will work for current domain
COOKIE_SECURE = True  # Only send over HTTPS
COOKIE_HTTPONLY = True  # Prevent JavaScript access
COOKIE_SAMESITE = "lax"  # CSRF protection


def generate_code(length=6) -> str:
    """Generate a random numeric code"""
    return ''.join(random.choices(string.digits, k=length))


@router.post("/signup", status_code=status.HTTP_201_CREATED)
async def signup(request: SignupRequest, response: Response):
    """
    Register a new developer account.
    Sets HttpOnly cookies with access and refresh tokens.
    Sends verification email with 6-digit code.
    """
    # Check if email already exists
    existing_developer = await Developer.find_one(Developer.email == request.email)
    if existing_developer:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email already registered"
        )

    # Generate verification code
    verification_code = generate_code(6)
    verification_expires = datetime.utcnow() + timedelta(minutes=15)

    # Create new developer
    hashed_password = get_password_hash(request.password)
    new_developer = Developer(
        email=request.email,
        hashed_password=hashed_password,
        first_name=request.first_name,
        last_name=request.last_name,
        company_name=request.company_name,
        verification_code=verification_code,
        verification_code_expires=verification_expires,
    )

    await new_developer.insert()

    # Send verification email
    await email_service.send_email(
        to_email=request.email,
        subject="Verify Your Email - URI Social SDK",
        template_name="email_verification",
        template_vars={
            "first_name": request.first_name,
            "verification_code": verification_code,
        }
    )

    # Generate tokens
    access_token = create_access_token(data={"sub": str(new_developer.id)})
    refresh_token = create_refresh_token(data={"sub": str(new_developer.id)})

    # Set HttpOnly cookies
    response.set_cookie(
        key=COOKIE_ACCESS_TOKEN_NAME,
        value=access_token,
        max_age=COOKIE_MAX_AGE,
        httponly=COOKIE_HTTPONLY,
        secure=COOKIE_SECURE,
        samesite=COOKIE_SAMESITE,
        domain=COOKIE_DOMAIN,
    )
    response.set_cookie(
        key=COOKIE_REFRESH_TOKEN_NAME,
        value=refresh_token,
        max_age=COOKIE_MAX_AGE,
        httponly=COOKIE_HTTPONLY,
        secure=COOKIE_SECURE,
        samesite=COOKIE_SAMESITE,
        domain=COOKIE_DOMAIN,
    )

    return {
        "message": "Signup successful. Please verify your email.",
        "email": new_developer.email,
        "requires_verification": True
    }


@router.post("/verify-email")
async def verify_email(request: VerifyEmailRequest):
    """Verify email with 6-digit code"""
    developer = await Developer.find_one(Developer.email == request.email)

    if not developer:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )

    if developer.is_verified:
        return {"message": "Email already verified"}

    if not developer.verification_code or not developer.verification_code_expires:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No verification code found. Please request a new one."
        )

    if datetime.utcnow() > developer.verification_code_expires:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Verification code expired. Please request a new one."
        )

    if developer.verification_code != request.code:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid verification code"
        )

    # Mark as verified and clear verification code
    developer.is_verified = True
    developer.verification_code = None
    developer.verification_code_expires = None
    developer.updated_at = datetime.utcnow()
    await developer.save()

    return {"message": "Email verified successfully"}


@router.post("/resend-verification")
async def resend_verification(request: ResendVerificationRequest):
    """Resend verification code"""
    developer = await Developer.find_one(Developer.email == request.email)

    if not developer:
        # Don't reveal if email exists
        return {"message": "If the email exists, a verification code has been sent"}

    if developer.is_verified:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email already verified"
        )

    # Generate new code
    verification_code = generate_code(6)
    verification_expires = datetime.utcnow() + timedelta(minutes=15)

    developer.verification_code = verification_code
    developer.verification_code_expires = verification_expires
    developer.updated_at = datetime.utcnow()
    await developer.save()

    # Send verification email
    await email_service.send_email(
        to_email=request.email,
        subject="Verify Your Email - URI Social SDK",
        template_name="email_verification",
        template_vars={
            "first_name": developer.first_name,
            "verification_code": verification_code,
        }
    )

    return {"message": "Verification code sent"}


@router.post("/login")
async def login(request: LoginRequest, response: Response):
    """
    Login with email and password.
    Sets HttpOnly cookies with access and refresh tokens.
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

    # Set HttpOnly cookies
    response.set_cookie(
        key=COOKIE_ACCESS_TOKEN_NAME,
        value=access_token,
        max_age=COOKIE_MAX_AGE,
        httponly=COOKIE_HTTPONLY,
        secure=COOKIE_SECURE,
        samesite=COOKIE_SAMESITE,
        domain=COOKIE_DOMAIN,
    )
    response.set_cookie(
        key=COOKIE_REFRESH_TOKEN_NAME,
        value=refresh_token,
        max_age=COOKIE_MAX_AGE,
        httponly=COOKIE_HTTPONLY,
        secure=COOKIE_SECURE,
        samesite=COOKIE_SAMESITE,
        domain=COOKIE_DOMAIN,
    )

    return {
        "message": "Login successful",
        "email": developer.email,
        "email_verified": developer.is_verified
    }


@router.post("/forgot-password")
async def forgot_password(request: ForgotPasswordRequest):
    """Send password reset code to email"""
    developer = await Developer.find_one(Developer.email == request.email)

    # Don't reveal if email exists
    if not developer:
        return {"message": "If the email exists, a reset code has been sent"}

    # Generate reset code
    reset_code = generate_code(6)
    reset_expires = datetime.utcnow() + timedelta(minutes=15)

    developer.reset_code = reset_code
    developer.reset_code_expires = reset_expires
    developer.updated_at = datetime.utcnow()
    await developer.save()

    # Send password reset email
    await email_service.send_email(
        to_email=request.email,
        subject="Reset Your Password - URI Social SDK",
        template_name="password_reset",
        template_vars={
            "first_name": developer.first_name,
            "reset_code": reset_code,
        }
    )

    return {"message": "If the email exists, a reset code has been sent"}


@router.post("/reset-password")
async def reset_password(request: ResetPasswordRequest):
    """Reset password using reset code"""
    developer = await Developer.find_one(Developer.email == request.email)

    if not developer:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )

    if not developer.reset_code or not developer.reset_code_expires:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No reset code found. Please request a new one."
        )

    if datetime.utcnow() > developer.reset_code_expires:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Reset code expired. Please request a new one."
        )

    if developer.reset_code != request.code:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid reset code"
        )

    # Update password and clear reset code
    developer.hashed_password = get_password_hash(request.new_password)
    developer.reset_code = None
    developer.reset_code_expires = None
    developer.updated_at = datetime.utcnow()
    await developer.save()

    return {"message": "Password reset successfully"}


@router.post("/change-password")
async def change_password(
    request: ChangePasswordRequest,
    current_developer: Developer = Depends(get_current_developer)
):
    """Change password for authenticated user"""
    # Verify current password
    if not verify_password(request.current_password, current_developer.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Current password is incorrect"
        )

    # Ensure new password is different
    if verify_password(request.new_password, current_developer.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="New password must be different from current password"
        )

    # Update password
    current_developer.hashed_password = get_password_hash(request.new_password)
    current_developer.updated_at = datetime.utcnow()
    await current_developer.save()

    return {"message": "Password changed successfully"}


@router.get("/me", response_model=DeveloperResponse)
async def get_current_user(current_developer: Developer = Depends(get_current_developer)):
    """
    Get current authenticated developer info.
    Protected route - requires valid JWT token.
    """
    return DeveloperResponse(
        id=str(current_developer.id),
        email=current_developer.email,
        first_name=current_developer.first_name,
        last_name=current_developer.last_name,
        company_name=current_developer.company_name,
        is_verified=current_developer.is_verified,
    )


@router.post("/logout")
async def logout(response: Response):
    """
    Logout by clearing HttpOnly cookies.
    """
    response.delete_cookie(key=COOKIE_ACCESS_TOKEN_NAME)
    response.delete_cookie(key=COOKIE_REFRESH_TOKEN_NAME)
    return {"message": "Successfully logged out"}


# Google OAuth Setup
oauth = OAuth()
oauth.register(
    name='google',
    client_id=settings.GOOGLE_CLIENT_ID,
    client_secret=settings.GOOGLE_CLIENT_SECRET,
    server_metadata_url='https://accounts.google.com/.well-known/openid-configuration',
    client_kwargs={'scope': 'openid email profile'},
)

# State serializer for OAuth security
state_serializer = URLSafeTimedSerializer(settings.SECRET_KEY, salt="google-oauth")


@router.get("/google")
async def google_login(request: Request):
    """
    Initiate Google OAuth login flow.
    Redirects user to Google's authorization page.
    """
    # Generate state token for CSRF protection
    state = state_serializer.dumps({"action": "login"})

    redirect_uri = settings.GOOGLE_REDIRECT_URI
    return await oauth.google.authorize_redirect(request, redirect_uri, state=state)


@router.get("/google/callback")
async def google_callback(request: Request, response: Response):
    """
    Handle Google OAuth callback.
    Creates or logs in user based on Google account info.
    """
    try:
        # Verify state token
        state = request.query_params.get('state')
        if not state:
            raise HTTPException(status_code=400, detail="Missing state parameter")

        try:
            state_data = state_serializer.loads(state, max_age=600)  # 10 minutes
        except Exception:
            raise HTTPException(status_code=400, detail="Invalid or expired state")

        # Exchange authorization code for token
        token = await oauth.google.authorize_access_token(request)

        # Get user info from Google
        user_info = token.get('userinfo')
        if not user_info:
            # Fallback: fetch userinfo manually
            async with httpx.AsyncClient() as client:
                resp = await client.get(
                    'https://www.googleapis.com/oauth2/v3/userinfo',
                    headers={'Authorization': f'Bearer {token["access_token"]}'}
                )
                user_info = resp.json()

        email = user_info.get('email')
        if not email:
            raise HTTPException(status_code=400, detail="Email not provided by Google")

        # Check if user exists
        developer = await Developer.find_one(Developer.email == email)

        if not developer:
            # Create new developer account
            developer = Developer(
                email=email,
                hashed_password="",  # No password for OAuth users
                first_name=user_info.get('given_name', ''),
                last_name=user_info.get('family_name', ''),
                is_verified=True,  # Google already verified the email
                oauth_provider="google",
                oauth_id=user_info.get('sub'),
            )
            await developer.insert()
        else:
            # Update OAuth info if not set
            if not developer.oauth_provider:
                developer.oauth_provider = "google"
                developer.oauth_id = user_info.get('sub')
                developer.is_verified = True
                developer.updated_at = datetime.utcnow()
                await developer.save()

        # Generate tokens
        access_token = create_access_token(data={"sub": str(developer.id)})
        refresh_token = create_refresh_token(data={"sub": str(developer.id)})

        # Create redirect response to frontend
        frontend_url = settings.FRONTEND_URL
        redirect_url = f"{frontend_url}/dashboard"

        # Create response with redirect
        redirect_response = RedirectResponse(url=redirect_url)

        # Set HttpOnly cookies
        redirect_response.set_cookie(
            key=COOKIE_ACCESS_TOKEN_NAME,
            value=access_token,
            max_age=COOKIE_MAX_AGE,
            httponly=COOKIE_HTTPONLY,
            secure=COOKIE_SECURE,
            samesite=COOKIE_SAMESITE,
            domain=COOKIE_DOMAIN,
        )
        redirect_response.set_cookie(
            key=COOKIE_REFRESH_TOKEN_NAME,
            value=refresh_token,
            max_age=COOKIE_MAX_AGE,
            httponly=COOKIE_HTTPONLY,
            secure=COOKIE_SECURE,
            samesite=COOKIE_SAMESITE,
            domain=COOKIE_DOMAIN,
        )

        return redirect_response

    except Exception as e:
        # Redirect to login with error
        error_url = f"{settings.FRONTEND_URL}/login?error=oauth_failed"
        return RedirectResponse(url=error_url)
