from fastapi import APIRouter

from app.api.v1.endpoints import auth, cameras, incidents, ws, zones

api_v1_router = APIRouter()
api_v1_router.include_router(auth.router)
api_v1_router.include_router(cameras.router)
api_v1_router.include_router(zones.router)
api_v1_router.include_router(incidents.router)
api_v1_router.include_router(ws.router)
