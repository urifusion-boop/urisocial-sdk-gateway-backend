from beanie import Document
from pydantic import Field
from datetime import datetime
from bson import ObjectId
import enum


class MemberRole(str, enum.Enum):
    OWNER = "owner"
    ADMIN = "admin"
    MEMBER = "member"
    VIEWER = "viewer"


class WorkspaceMember(Document):
    workspace_id: ObjectId = Field(index=True)
    developer_id: ObjectId = Field(index=True)
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
