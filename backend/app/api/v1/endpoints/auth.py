from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, require_roles
from app.core.security import TokenError, create_access_token, create_refresh_token, decode_token
from app.db.session import get_db_session
from app.models.enums import UserRole
from app.models.user import User
from app.schemas.auth import LoginRequest, RefreshRequest, TokenPairResponse, UserMeResponse
from app.services.auth_service import authenticate_user, get_user_by_id

router = APIRouter(prefix="/auth", tags=["auth"])


def _build_token_pair(user: User) -> TokenPairResponse:
    role_value = user.role.value if isinstance(user.role, UserRole) else str(user.role)
    return TokenPairResponse(
        access_token=create_access_token(subject=user.id, role=role_value),
        refresh_token=create_refresh_token(subject=user.id, role=role_value),
    )


@router.post("/login", response_model=TokenPairResponse)
async def login(payload: LoginRequest, session: AsyncSession = Depends(get_db_session)) -> TokenPairResponse:
    user = await authenticate_user(
        session,
        username=payload.username,
        password=payload.password,
    )
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid username or password",
        )

    return _build_token_pair(user)


@router.post("/refresh", response_model=TokenPairResponse)
async def refresh(payload: RefreshRequest, session: AsyncSession = Depends(get_db_session)) -> TokenPairResponse:
    try:
        decoded = decode_token(payload.refresh_token, expected_type="refresh")
        user_id = int(decoded["sub"])
    except (TokenError, KeyError, ValueError):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid refresh token",
        ) from None

    user = await get_user_by_id(session, user_id)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid refresh token",
        )

    return _build_token_pair(user)


@router.get("/me", response_model=UserMeResponse)
async def me(current_user: User = Depends(get_current_user)) -> UserMeResponse:
    return UserMeResponse.model_validate(current_user)


@router.get("/admin-only", response_model=UserMeResponse)
async def admin_only(
    current_user: User = Depends(require_roles(UserRole.admin)),
) -> UserMeResponse:
    return UserMeResponse.model_validate(current_user)

