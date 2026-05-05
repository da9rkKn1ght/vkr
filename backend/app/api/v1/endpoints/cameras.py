import base64
import time

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_roles
from app.db.session import get_db_session
from app.models.camera import Camera
from app.models.enums import UserRole
from app.schemas.camera import CameraCreate, CameraResponse, CameraUpdate

router = APIRouter(prefix="/cameras", tags=["cameras"])

READ_CAMERA = Depends(require_roles(UserRole.admin, UserRole.manager))
WRITE_CAMERA = Depends(require_roles(UserRole.admin))


def _parse_source(source: str) -> str | int:
    cleaned = source.strip()
    if cleaned.isdigit():
        return int(cleaned)
    return cleaned


def _capture_snapshot(rtsp_url: str) -> bytes | None:
    try:
        import cv2
    except ModuleNotFoundError:
        return None

    capture = cv2.VideoCapture(_parse_source(rtsp_url))
    if not capture.isOpened():
        capture.release()
        return None

    try:
        frame = None
        for _ in range(60):
            ok, current_frame = capture.read()
            if ok and current_frame is not None:
                frame = current_frame
                break
            time.sleep(0.05)
        if frame is None:
            return None

        ok, encoded = cv2.imencode(".jpg", frame)
        if not ok:
            return None
        return encoded.tobytes()
    finally:
        capture.release()


@router.get("", response_model=list[CameraResponse], dependencies=[READ_CAMERA])
async def list_cameras(session: AsyncSession = Depends(get_db_session)) -> list[Camera]:
    result = await session.execute(select(Camera).order_by(Camera.id.asc()))
    return list(result.scalars().all())


@router.get("/{camera_id}", response_model=CameraResponse, dependencies=[READ_CAMERA])
async def get_camera(camera_id: int, session: AsyncSession = Depends(get_db_session)) -> Camera:
    camera = await session.get(Camera, camera_id)
    if camera is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Camera not found")
    return camera


@router.get("/{camera_id}/snapshot", dependencies=[READ_CAMERA])
async def get_camera_snapshot(camera_id: int, session: AsyncSession = Depends(get_db_session)) -> dict[str, str]:
    camera = await session.get(Camera, camera_id)
    if camera is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Camera not found")

    snapshot_bytes = _capture_snapshot(camera.rtsp_url)
    if snapshot_bytes is None:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Failed to capture snapshot from camera stream",
        )

    return {
        "mime_type": "image/jpeg",
        "image_base64": base64.b64encode(snapshot_bytes).decode("ascii"),
    }


@router.post(
    "",
    response_model=CameraResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[WRITE_CAMERA],
)
async def create_camera(payload: CameraCreate, session: AsyncSession = Depends(get_db_session)) -> Camera:
    camera = Camera(
        name=payload.name,
        rtsp_url=payload.rtsp_url,
        is_active=payload.is_active,
    )
    session.add(camera)
    await session.commit()
    await session.refresh(camera)
    return camera


@router.put("/{camera_id}", response_model=CameraResponse, dependencies=[WRITE_CAMERA])
async def update_camera(
    camera_id: int,
    payload: CameraUpdate,
    session: AsyncSession = Depends(get_db_session),
) -> Camera:
    camera = await session.get(Camera, camera_id)
    if camera is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Camera not found")

    updates = payload.model_dump(exclude_unset=True)
    for field, value in updates.items():
        setattr(camera, field, value)

    await session.commit()
    await session.refresh(camera)
    return camera


@router.delete("/{camera_id}", status_code=status.HTTP_204_NO_CONTENT, dependencies=[WRITE_CAMERA])
async def delete_camera(camera_id: int, session: AsyncSession = Depends(get_db_session)) -> Response:
    camera = await session.get(Camera, camera_id)
    if camera is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Camera not found")

    await session.delete(camera)
    await session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
