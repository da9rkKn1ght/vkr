from datetime import datetime, timezone

import pytest
from httpx import AsyncClient
from sqlalchemy import select

from app.db.session import get_session_maker
from app.models.incident import Incident


async def _login(client: AsyncClient, username: str, password: str) -> str:
    response = await client.post(
        "/api/v1/auth/login",
        json={"username": username, "password": password},
    )
    assert response.status_code == 200
    return response.json()["access_token"]


@pytest.mark.asyncio
async def test_post_incident_saves_to_db_and_broadcasts(
    client: AsyncClient,
    seeded_users: dict[str, str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    admin_token = await _login(client, seeded_users["admin_username"], seeded_users["admin_password"])

    camera_response = await client.post(
        "/api/v1/cameras",
        json={"name": "Worker Cam", "rtsp_url": "rtsp://camera/worker", "is_active": True},
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert camera_response.status_code == 201
    camera_id = camera_response.json()["id"]

    broadcast_calls: list[dict] = []

    async def fake_broadcast(message: dict) -> None:
        broadcast_calls.append(message)

    monkeypatch.setattr("app.api.v1.endpoints.incidents.ws_connection_manager.broadcast_json", fake_broadcast)

    timestamp = datetime.now(timezone.utc).replace(microsecond=0)
    create_response = await client.post(
        "/api/v1/incidents",
        json={
            "camera_id": camera_id,
            "type": "sleep",
            "timestamp": timestamp.isoformat().replace("+00:00", "Z"),
            "image_path": "/uploads/incidents/sleep_001.jpg",
        },
    )
    assert create_response.status_code == 201
    payload = create_response.json()
    assert payload["camera_id"] == camera_id
    assert payload["type"] == "sleep"
    assert payload["image_path"] == "/uploads/incidents/sleep_001.jpg"

    session_maker = get_session_maker()
    async with session_maker() as session:
        result = await session.execute(select(Incident).where(Incident.id == payload["id"]))
        created_incident = result.scalar_one_or_none()

    assert created_incident is not None
    assert created_incident.camera_id == camera_id
    assert created_incident.image_path == "/uploads/incidents/sleep_001.jpg"

    assert len(broadcast_calls) == 1
    assert broadcast_calls[0]["event"] == "incident_created"
    assert broadcast_calls[0]["data"]["id"] == payload["id"]
    assert broadcast_calls[0]["data"]["type"] == "sleep"

