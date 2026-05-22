from beanie import Document, PydanticObjectId
from pydantic import Field
from datetime import datetime
import enum


class MemberRole(str, enum.Enum):
    OWNER = "owner"
    ADMIN = "admin"
    MEMBER = "member"
    VIEWER = "viewer"


class WorkspaceMember(Document):
    workspace_id: PydanticObjectId = Field(index=True)
    developer_id: PydanticObjectId = Field(index=True)
    role: MemberRole = MemberRole.MEMBER

    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)

    class Settings:
        name = "workspace_members"
        indexes = [
            "workspace_id",
            "developer_id",
            ("workspace_id", "developer_id"),  # Compound index
        ]

    class Config:
        json_schema_extra = {
            "example": {
                "role": "member",
            }
        }
