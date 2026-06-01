from fastapi import APIRouter
from app.api.v1.endpoints import auth, keys, webhooks, proxy, billing

api_router = APIRouter()

api_router.include_router(auth.router, prefix="/auth", tags=["Authentication"])
api_router.include_router(keys.router, prefix="/keys", tags=["API Keys"])
api_router.include_router(webhooks.router, prefix="/webhooks", tags=["Webhooks"])
api_router.include_router(billing.router, tags=["Billing"])

# Proxy router (no prefix - routes defined in router itself)
api_router.include_router(proxy.router, tags=["Proxy"])
