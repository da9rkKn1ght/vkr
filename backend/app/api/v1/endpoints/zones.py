from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_roles
from app.db.session import get_db_session
from app.models.camera import Camera
from app.models.enums import UserRole
from app.models.zone import Zone
from app.schemas.zone import ZoneCreate, ZoneResponse, ZoneUpdate

router = APIRouter(prefix="/zones", tags=["zones"])

READ_ZONE = Depends(require_roles(UserRole.admin, UserRole.manager))
WRITE_ZONE = Depends(require_roles(UserRole.admin))


async def _ensure_camera_exists(session: AsyncSession, camera_id: int) -> None:
    camera = await session.get(Camera, camera_id)
    if camera is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Camera not found")


@router.get("", response_model=list[ZoneResponse], dependencies=[READ_ZONE])
async def list_zones(
    camera_id: int | None = Query(default=None, gt=0),
    session: AsyncSession = Depends(get_db_session),
) -> list[Zone]:
    query = select(Zone).order_by(Zone.id.asc())
    if camera_id is not None:
        query = query.where(Zone.camera_id == camera_id)

    result = await session.execute(query)
    return list(result.scalars().all())


@router.get("/{zone_id}", response_model=ZoneResponse, dependencies=[READ_ZONE])
async def get_zone(zone_id: int, session: AsyncSession = Depends(get_db_session)) -> Zone:
    zone = await session.get(Zone, zone_id)
    if zone is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Zone not found")
    return zone


@router.post("", response_model=ZoneResponse, status_code=status.HTTP_201_CREATED, dependencies=[WRITE_ZONE])
async def create_zone(payload: ZoneCreate, session: AsyncSession = Depends(get_db_session)) -> Zone:
    await _ensure_camera_exists(session, payload.camera_id)

    zone = Zone(camera_id=payload.camera_id, coordinates=payload.coordinates)
    session.add(zone)
    await session.commit()
    await session.refresh(zone)
    return zone


@router.put("/{zone_id}", response_model=ZoneResponse, dependencies=[WRITE_ZONE])
async def update_zone(
    zone_id: int,
    payload: ZoneUpdate,
    session: AsyncSession = Depends(get_db_session),
) -> Zone:
    zone = await session.get(Zone, zone_id)
    if zone is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Zone not found")

    updates = payload.model_dump(exclude_unset=True)
    new_camera_id = updates.get("camera_id")
    if new_camera_id is not None:
        await _ensure_camera_exists(session, new_camera_id)

    for field, value in updates.items():
        setattr(zone, field, value)

    await session.commit()
    await session.refresh(zone)
    return zone


@router.delete("/{zone_id}", status_code=status.HTTP_204_NO_CONTENT, dependencies=[WRITE_ZONE])
async def delete_zone(zone_id: int, session: AsyncSession = Depends(get_db_session)) -> Response:
    zone = await session.get(Zone, zone_id)
    if zone is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Zone not found")

    await session.delete(zone)
    await session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)

