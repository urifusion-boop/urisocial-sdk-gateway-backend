# URI Social Gateway Backend

Enterprise-grade FastAPI backend for the URI Social Developer Platform using MongoDB.

## Tech Stack

- **FastAPI 0.115.0** - Modern async Python web framework
- **MongoDB** - NoSQL database with Beanie ODM
- **Beanie 1.26.0** - Async MongoDB ODM (like SQLAlchemy for MongoDB)
- **Motor 3.6.0** - Async MongoDB driver
- **JWT Authentication** - Secure token-based auth
- **Redis** - Rate limiting and caching

## Features

- **Developer Authentication**: JWT-based auth with signup/login
- **API Key Management**: Generate and manage API keys
- **Workspace Management**: Multi-tenant workspace support
- **Usage Tracking**: Track API usage and analytics
- **Rate Limiting**: Redis-based rate limiting
- **Async/Await**: Full async support for high performance

## Setup

### 1. Create virtual environment:
```bash
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

### 2. Install dependencies:
```bash
pip install -r requirements.txt
```

### 3. Setup MongoDB:

**Option A: Local MongoDB**
```bash
# Install MongoDB (macOS)
brew tap mongodb/brew
brew install mongodb-community

# Start MongoDB
brew services start mongodb-community
```

**Option B: MongoDB Atlas (Cloud)**
- Sign up at https://www.mongodb.com/cloud/atlas
- Create a free cluster
- Get connection string

### 4. Setup environment variables:
```bash
cp .env.example .env
```

Edit `.env`:
```env
MONGODB_URL=mongodb://localhost:27017  # or your Atlas connection string
DATABASE_NAME=uri_gateway_dev
SECRET_KEY=your-super-secret-key-change-this
ALGORITHM=HS256
ACCESS_TOKEN_EXPIRE_MINUTES=30
REFRESH_TOKEN_EXPIRE_DAYS=7
REDIS_URL=redis://localhost:6379
FRONTEND_URL=http://localhost:3000
ENVIRONMENT=development
API_KEY_PREFIX=urisocial_
```

### 5. Run development server:
```bash
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

The server will:
- Connect to MongoDB on startup
- Initialize Beanie ODM with all document models
- Create indexes automatically
- Start accepting requests at http://localhost:8000

## API Documentation

- **Swagger UI**: http://localhost:8000/docs
- **ReDoc**: http://localhost:8000/redoc
- **Health Check**: http://localhost:8000/health

## Project Structure (Enterprise Pattern)

```
app/
├── main.py                 # FastAPI app with lifespan events
├── core/
│   ├── config.py          # Settings and configuration
│   └── security.py        # JWT and password hashing
├── db/
│   └── mongodb.py         # MongoDB connection and Beanie init
├── models/                # Beanie Document models (MongoDB collections)
│   ├── developer.py       # Developer accounts
│   ├── api_key.py         # API keys
│   ├── workspace.py       # Workspaces
│   ├── workspace_member.py # Team members
│   └── usage_log.py       # Usage analytics
├── schemas/               # Pydantic request/response schemas
│   └── auth.py            # Auth DTOs
├── api/
│   ├── deps.py            # Dependency injection (auth, etc.)
│   └── v1/
│       ├── api.py         # Router aggregation
│       └── endpoints/
│           └── auth.py    # Auth endpoints
└── services/              # Business logic layer (coming soon)
```

## MongoDB vs SQL Differences

### No Migrations Needed
- MongoDB is schema-less (no Alembic needed)
- Beanie creates indexes automatically on startup
- Add/remove fields without migrations

### Document Model Example
```python
from beanie import Document
from pydantic import EmailStr, Field

class Developer(Document):
    email: EmailStr = Field(unique=True, index=True)
    hashed_password: str

    class Settings:
        name = "developers"  # Collection name
        indexes = ["email"]
```

### Async Queries
```python
# Find one
developer = await Developer.find_one(Developer.email == "dev@example.com")

# Insert
await new_developer.insert()

# Find many
developers = await Developer.find(Developer.is_active == True).to_list()
```

## Authentication Flow

1. **Signup**: `POST /api/v1/auth/signup`
   - Creates developer account in MongoDB
   - Returns JWT access + refresh tokens

2. **Login**: `POST /api/v1/auth/login`
   - Validates credentials
   - Returns JWT tokens

3. **Protected Routes**: Include `Authorization: Bearer <token>` header
   - Backend validates JWT
   - Returns developer object via dependency injection

4. **Get Current User**: `GET /api/v1/auth/me`
   - Requires valid JWT
   - Returns developer profile

## Protected Routes

Use the `get_current_developer` dependency:

```python
from app.api.deps import get_current_developer
from app.models.developer import Developer

@router.get("/protected")
async def protected_route(
    current_developer: Developer = Depends(get_current_developer)
):
    return {"message": f"Hello {current_developer.email}"}
```

## Database Models

### Collections in MongoDB:

1. **developers** - Developer accounts
   - email (unique, indexed)
   - hashed_password
   - first_name, last_name, company_name
   - is_active, is_verified
   - created_at, updated_at

2. **api_keys** - API keys for SDK authentication
   - key (hashed, unique, indexed)
   - key_prefix (for display)
   - name, description
   - developer_id (indexed)
   - workspace_id
   - is_active, last_used_at, expires_at

3. **workspaces** - Multi-tenant workspaces
   - name, slug (unique, indexed)
   - owner_id (indexed)
   - subscription_tier (free/pro/enterprise)
   - monthly_request_limit, monthly_requests_used

4. **workspace_members** - Team collaboration
   - workspace_id, developer_id (compound index)
   - role (owner/admin/member/viewer)

5. **usage_logs** - API usage analytics
   - api_key_id (indexed)
   - endpoint, method, status_code
   - response_time_ms, ip_address
   - created_at (indexed)

## Development

### Running Tests
```bash
pytest
```

### Linting
```bash
black app/
flake8 app/
```

### Docker (Coming Soon)
```bash
docker-compose up
```

## Deployment

Backend can be deployed to:
- **Azure Container Apps** (recommended)
- **Azure App Service**
- **Vercel** (with serverless functions)
- **Railway**
- **Fly.io**

Frontend (Next.js) deploys to **Azure Static Web Apps**
# urisocial-sdk-gateway-backend
