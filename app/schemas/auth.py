from pydantic import BaseModel, EmailStr, Field
from typing import Optional


class SignupRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8)
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    company_name: Optional[str] = None


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class VerifyEmailRequest(BaseModel):
    email: EmailStr
    code: str = Field(min_length=6, max_length=6)


class ResendVerificationRequest(BaseModel):
    email: EmailStr


class ForgotPasswordRequest(BaseModel):
    email: EmailStr


class ResetPasswordRequest(BaseModel):
    email: EmailStr
    code: str = Field(min_length=6, max_length=6)
    new_password: str = Field(min_length=8)


class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str = Field(min_length=8)


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class DeveloperResponse(BaseModel):
    id: str
    email: str
    first_name: Optional[str]
    last_name: Optional[str]
    company_name: Optional[str]
    is_verified: bool

    class Config:
        from_attributes = True
        json_encoders = {
            object: str
        }
