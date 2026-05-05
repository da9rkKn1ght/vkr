import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_login_success_returns_tokens(
    client: AsyncClient,
    seeded_users: dict[str, str],
) -> None:
    response = await client.post(
        "/api/v1/auth/login",
        json={
            "username": seeded_users["admin_username"],
            "password": seeded_users["admin_password"],
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["token_type"] == "bearer"
    assert payload["access_token"]
    assert payload["refresh_token"]


@pytest.mark.asyncio
async def test_login_fails_for_bad_credentials(
    client: AsyncClient,
    seeded_users: dict[str, str],
) -> None:
    response = await client.post(
        "/api/v1/auth/login",
        json={
            "username": seeded_users["admin_username"],
            "password": "bad_password",
        },
    )

    assert response.status_code == 401
    assert response.json()["detail"] == "Invalid username or password"


@pytest.mark.asyncio
async def test_refresh_returns_new_pair(
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
    login_payload = login_response.json()

    refresh_response = await client.post(
        "/api/v1/auth/refresh",
        json={"refresh_token": login_payload["refresh_token"]},
    )

    assert refresh_response.status_code == 200
    refresh_payload = refresh_response.json()
    assert refresh_payload["access_token"]
    assert refresh_payload["refresh_token"]


@pytest.mark.asyncio
async def test_me_returns_current_user(
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
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {access_token}"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["username"] == seeded_users["manager_username"]
    assert payload["role"] == "manager"

