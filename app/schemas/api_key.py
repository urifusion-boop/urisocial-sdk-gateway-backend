from pydantic import BaseModel, Field
from datetime import datetime
from typing import Optional, List

from app.models.api_key import APIKeyScope


class CreateAPIKeyRequest(BaseModel):
    """Request schema for creating a new API key"""
    name: str = Field(..., min_length=1, max_length=100, description="Name for the API key")
    description: Optional[str] = Field(None, max_length=500, description="Optional description")
    scopes: Optional[List[APIKeyScope]] = Field(None, description="Permission scopes for this key")
    whitelisted_ips: Optional[List[str]] = Field(None, description="IP whitelist (CIDR or single IPs)")
    environment: Optional[str] = Field(None, description="Environment tag (production, development, staging)")
    rotation_enabled: Optional[bool] = Field(False, description="Enable automatic key rotation")
    rotation_days: Optional[int] = Field(90, description="Days between automatic rotations")


class CreateAPIKeyResponse(BaseModel):
    """Response schema for creating a new API key"""
    api_key: str = Field(..., description="The full API key - ONLY SHOWN ONCE!")
    key_id: str = Field(..., description="Unique identifier for this key")
    key_prefix: str = Field(..., description="First 15 chars for display")
    name: str
    description: Optional[str] = None
    created_at: datetime
    warning: str = Field(
        default="⚠️ Save this API key securely! You won't be able to see it again.",
        description="Security warning"
    )


class APIKeyResponse(BaseModel):
    """Response schema for API key (without sensitive data)"""
    id: str
    key_prefix: str
    name: str
    description: Optional[str] = None
    is_active: bool
    created_at: datetime
    last_used_at: Optional[datetime] = None
    expires_at: Optional[datetime] = None

    # Advanced features
    scopes: List[APIKeyScope] = []
    whitelisted_ips: List[str] = []
    environment: Optional[str] = None
    rotation_enabled: bool = False
    rotation_days: Optional[int] = None
    last_rotated_at: Optional[datetime] = None
    next_rotation_at: Optional[datetime] = None

    # Metadata
    last_ip_address: Optional[str] = None
    user_agent: Optional[str] = None


class UpdateAPIKeyRequest(BaseModel):
    """Request schema for updating an API key"""
    name: Optional[str] = Field(None, min_length=1, max_length=100)
    description: Optional[str] = Field(None, max_length=500)
    scopes: Optional[List[APIKeyScope]] = None
    whitelisted_ips: Optional[List[str]] = None
    environment: Optional[str] = None
    rotation_enabled: Optional[bool] = None
    rotation_days: Optional[int] = None
