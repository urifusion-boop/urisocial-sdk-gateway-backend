from motor.motor_asyncio import AsyncIOMotorClient
from beanie import init_beanie
from app.core.config import settings
from app.models.developer import Developer
from app.models.api_key import APIKey
from app.models.workspace import Workspace
from app.models.workspace_member import WorkspaceMember
from app.models.usage_log import UsageLog


class MongoDB:
    client: AsyncIOMotorClient = None


mongodb = MongoDB()


async def connect_to_mongodb():
    """Connect to MongoDB and initialize Beanie ODM."""
    mongodb.client = AsyncIOMotorClient(settings.MONGODB_URL)

    await init_beanie(
        database=mongodb.client[settings.DATABASE_NAME],
        document_models=[
            Developer,
            APIKey,
            Workspace,
            WorkspaceMember,
            UsageLog,
        ],
    )
    print(f"✅ Connected to MongoDB: {settings.DATABASE_NAME}")


async def close_mongodb_connection():
    """Close MongoDB connection."""
    if mongodb.client:
        mongodb.client.close()
        print("❌ MongoDB connection closed")


def get_database():
    """Get MongoDB database instance."""
    return mongodb.client[settings.DATABASE_NAME]
