from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_roles
from app.db.session import get_db_session
from app.models.camera import Camera
from app.models.enums import IncidentType, UserRole
from app.models.incident import Incident
from app.schemas.incident import IncidentCreateRequest, IncidentListResponse, IncidentResponse
from app.services.websockets import ws_connection_manager

router = APIRouter(prefix="/incidents", tags=["incidents"])

READ_INCIDENTS = Depends(require_roles(UserRole.admin, UserRole.manager))


@router.post("", response_model=IncidentResponse, status_code=status.HTTP_201_CREATED)
async def create_incident(
    payload: IncidentCreateRequest,
    session: AsyncSession = Depends(get_db_session),
) -> IncidentResponse:
    camera = await session.get(Camera, payload.camera_id)
    if camera is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Camera not found")

    incident = Incident(
        camera_id=payload.camera_id,
        type=payload.type,
        timestamp=payload.timestamp,
        image_path=payload.image_path,
    )
    session.add(incident)
    await session.commit()
    await session.refresh(incident)

    incident_payload = IncidentResponse.model_validate(incident).model_dump(mode="json")
    await ws_connection_manager.broadcast_json(
        {
            "event": "incident_created",
            "data": incident_payload,
        }
    )

    return IncidentResponse.model_validate(incident)


@router.get("", response_model=IncidentListResponse, dependencies=[READ_INCIDENTS])
async def list_incidents(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    camera_id: int | None = Query(default=None, gt=0),
    type: IncidentType | None = Query(default=None),
    session: AsyncSession = Depends(get_db_session),
) -> IncidentListResponse:
    filters = []
    if camera_id is not None:
        filters.append(Incident.camera_id == camera_id)
    if type is not None:
        filters.append(Incident.type == type)

    count_query = select(func.count()).select_from(Incident)
    data_query = select(Incident)
    if filters:
        count_query = count_query.where(*filters)
        data_query = data_query.where(*filters)

    total = int((await session.scalar(count_query)) or 0)
    offset = (page - 1) * page_size

    data_query = data_query.order_by(Incident.timestamp.desc(), Incident.id.desc()).offset(offset).limit(page_size)
    result = await session.execute(data_query)

    return IncidentListResponse(
        items=list(result.scalars().all()),
        page=page,
        page_size=page_size,
        total=total,
    )
