import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_admin_only_endpoint_denies_manager(
    client: AsyncClient,
    seeded_users: dict[str, str],
) -> None:
    login_response = await client.post(
        "/api/v1/auth/login",
        json={
            "username": seeded_users["manager_username"],
            "password": seeded_users["manager_password"],
        },
    )
    access_token = login_response.json()["access_token"]

    response = await client.get(
        "/api/v1/auth/admin-only",
        headers={"Authorization": f"Bearer {access_token}"},
    )

    assert response.status_code == 403
    assert response.json()["detail"] == "Insufficient permissions"


@pytest.mark.asyncio
async def test_admin_only_endpoint_allows_admin(
    client: AsyncClient,
    seeded_users: dict[str, str],
) -> None:
    login_response = await client.post(
        "/api/v1/auth/login",
        json={
            "username": seeded_users["admin_username"],
            "password": seeded_users["admin_password"],
        },
    )
    access_token = login_response.json()["access_token"]

    response = await client.get(
        "/api/v1/auth/admin-only",
        headers={"Authorization": f"Bearer {access_token}"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["username"] == seeded_users["admin_username"]
    assert payload["role"] == "admin"

