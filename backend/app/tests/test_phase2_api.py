from datetime import datetime, timedelta, timezone

import pytest
from httpx import AsyncClient

from app.api.v1.endpoints import cameras as cameras_endpoint
from app.db.session import get_session_maker
from app.models.enums import IncidentType
from app.models.incident import Incident


async def _login(client: AsyncClient, username: str, password: str) -> str:
    response = await client.post(
        "/api/v1/auth/login",
        json={"username": username, "password": password},
    )
    assert response.status_code == 200
    return response.json()["access_token"]


@pytest.mark.asyncio
async def test_cameras_crud_with_admin_and_manager_permissions(
    client: AsyncClient,
    seeded_users: dict[str, str],
) -> None:
    admin_token = await _login(client, seeded_users["admin_username"], seeded_users["admin_password"])
    manager_token = await _login(client, seeded_users["manager_username"], seeded_users["manager_password"])

    manager_create = await client.post(
        "/api/v1/cameras",
        json={"name": "Cam 01", "rtsp_url": "rtsp://camera/1", "is_active": True},
        headers={"Authorization": f"Bearer {manager_token}"},
    )
    assert manager_create.status_code == 403

    create_response = await client.post(
        "/api/v1/cameras",
        json={"name": "Cam 01", "rtsp_url": "rtsp://camera/1", "is_active": True},
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert create_response.status_code == 201
    camera_id = create_response.json()["id"]

    list_response = await client.get("/api/v1/cameras", headers={"Authorization": f"Bearer {manager_token}"})
    assert list_response.status_code == 200
    assert any(camera["id"] == camera_id for camera in list_response.json())

    update_response = await client.put(
        f"/api/v1/cameras/{camera_id}",
        json={"name": "Cam 01 Updated", "is_active": False},
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert update_response.status_code == 200
    assert update_response.json()["name"] == "Cam 01 Updated"
    assert update_response.json()["is_active"] is False

    manager_delete = await client.delete(
        f"/api/v1/cameras/{camera_id}",
        headers={"Authorization": f"Bearer {manager_token}"},
    )
    assert manager_delete.status_code == 403

    admin_delete = await client.delete(
        f"/api/v1/cameras/{camera_id}",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert admin_delete.status_code == 204

    get_after_delete = await client.get(
        f"/api/v1/cameras/{camera_id}",
        headers={"Authorization": f"Bearer {manager_token}"},
    )
    assert get_after_delete.status_code == 404


@pytest.mark.asyncio
async def test_zones_crud_and_coordinates_validation(
    client: AsyncClient,
    seeded_users: dict[str, str],
) -> None:
    admin_token = await _login(client, seeded_users["admin_username"], seeded_users["admin_password"])
    manager_token = await _login(client, seeded_users["manager_username"], seeded_users["manager_password"])

    camera_response = await client.post(
        "/api/v1/cameras",
        json={"name": "Zone Cam", "rtsp_url": "rtsp://camera/zone", "is_active": True},
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    camera_id = camera_response.json()["id"]

    zone_create = await client.post(
        "/api/v1/zones",
        json={"camera_id": camera_id, "coordinates": [[10, 20], [30, 40], [50, 60]]},
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert zone_create.status_code == 201
    zone_id = zone_create.json()["id"]

    zone_invalid = await client.post(
        "/api/v1/zones",
        json={"camera_id": camera_id, "coordinates": [[1, 2, 3]]},
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert zone_invalid.status_code == 422

    manager_create_zone = await client.post(
        "/api/v1/zones",
        json={"camera_id": camera_id, "coordinates": [[1, 2], [3, 4]]},
        headers={"Authorization": f"Bearer {manager_token}"},
    )
    assert manager_create_zone.status_code == 403

    manager_list = await client.get(
        f"/api/v1/zones?camera_id={camera_id}",
        headers={"Authorization": f"Bearer {manager_token}"},
    )
    assert manager_list.status_code == 200
    assert any(zone["id"] == zone_id for zone in manager_list.json())

    zone_update = await client.put(
        f"/api/v1/zones/{zone_id}",
        json={"coordinates": [[11, 22], [33, 44], [55, 66]]},
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert zone_update.status_code == 200
    assert zone_update.json()["coordinates"][0] == [11.0, 22.0]

    zone_delete = await client.delete(
        f"/api/v1/zones/{zone_id}",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert zone_delete.status_code == 204


@pytest.mark.asyncio
async def test_incidents_pagination_filters_and_sorting_desc(
    client: AsyncClient,
    seeded_users: dict[str, str],
) -> None:
    admin_token = await _login(client, seeded_users["admin_username"], seeded_users["admin_password"])
    manager_token = await _login(client, seeded_users["manager_username"], seeded_users["manager_password"])

    camera_response = await client.post(
        "/api/v1/cameras",
        json={"name": "Incidents Cam", "rtsp_url": "rtsp://camera/incidents", "is_active": True},
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    camera_id = camera_response.json()["id"]

    base_time = datetime.now(timezone.utc).replace(microsecond=0)
    session_maker = get_session_maker()
    async with session_maker() as session:
        session.add_all(
            [
                Incident(
                    camera_id=camera_id,
                    type=IncidentType.absence,
                    timestamp=base_time - timedelta(minutes=3),
                    image_path="/uploads/incidents/absence_1.jpg",
                ),
                Incident(
                    camera_id=camera_id,
                    type=IncidentType.phone,
                    timestamp=base_time - timedelta(minutes=1),
                    image_path="/uploads/incidents/phone_1.jpg",
                ),
                Incident(
                    camera_id=camera_id,
                    type=IncidentType.sleep,
                    timestamp=base_time - timedelta(minutes=2),
                    image_path="/uploads/incidents/sleep_1.jpg",
                ),
            ]
        )
        await session.commit()

    page_response = await client.get(
        "/api/v1/incidents?page=1&page_size=2",
        headers={"Authorization": f"Bearer {manager_token}"},
    )
    assert page_response.status_code == 200
    page_payload = page_response.json()
    assert page_payload["total"] == 3
    assert len(page_payload["items"]) == 2
    timestamps = [datetime.fromisoformat(item["timestamp"]) for item in page_payload["items"]]
    assert timestamps[0] >= timestamps[1]

    filter_response = await client.get(
        f"/api/v1/incidents?page=1&page_size=10&camera_id={camera_id}&type=phone",
        headers={"Authorization": f"Bearer {manager_token}"},
    )
    assert filter_response.status_code == 200
    filter_payload = filter_response.json()
    assert filter_payload["total"] == 1
    assert filter_payload["items"][0]["type"] == "phone"


@pytest.mark.asyncio
async def test_camera_snapshot_endpoint_returns_base64_jpeg(
    client: AsyncClient,
    seeded_users: dict[str, str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    admin_token = await _login(client, seeded_users["admin_username"], seeded_users["admin_password"])
    manager_token = await _login(client, seeded_users["manager_username"], seeded_users["manager_password"])

    create_response = await client.post(
        "/api/v1/cameras",
        json={"name": "Snapshot Cam", "rtsp_url": "rtsp://camera/snapshot", "is_active": True},
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert create_response.status_code == 201
    camera_id = create_response.json()["id"]

    monkeypatch.setattr(cameras_endpoint, "_capture_snapshot", lambda _source: b"fake-jpeg-bytes")

    snapshot_response = await client.get(
        f"/api/v1/cameras/{camera_id}/snapshot",
        headers={"Authorization": f"Bearer {manager_token}"},
    )
    assert snapshot_response.status_code == 200
    payload = snapshot_response.json()
    assert payload["mime_type"] == "image/jpeg"
    assert payload["image_base64"]
