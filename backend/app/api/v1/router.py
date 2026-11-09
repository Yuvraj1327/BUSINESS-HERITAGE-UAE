from fastapi import APIRouter

from app.api.v1 import auth, branches, health, users

api_router = APIRouter()
api_router.include_router(health.router)
api_router.include_router(auth.router)
api_router.include_router(branches.router)
api_router.include_router(users.router)
# Business routers are registered here in later steps (modules in Steps 7-11).
