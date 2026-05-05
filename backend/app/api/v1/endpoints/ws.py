from fastapi import APIRouter, WebSocket, WebSocketDisconnect, status

from app.core.security import TokenError, decode_token
from app.db.session import get_session_maker
from app.services.auth_service import get_user_by_id
from app.services.websockets import ws_connection_manager

router = APIRouter(tags=["ws"])


def _extract_bearer_token(authorization_header: str | None) -> str | None:
    if not authorization_header:
        return None

    prefix = "bearer "
    if not authorization_header.lower().startswith(prefix):
        return None

    return authorization_header[len(prefix) :].strip()


async def _is_valid_access_token(token: str) -> bool:
    try:
        payload = decode_token(token, expected_type="access")
        user_id = int(payload["sub"])
    except (TokenError, KeyError, ValueError):
        return False

    session_maker = get_session_maker()
    async with session_maker() as session:
        user = await get_user_by_id(session, user_id)
        return user is not None


@router.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket) -> None:
    query_token = websocket.query_params.get("token")
    header_token = _extract_bearer_token(websocket.headers.get("authorization"))
    token = query_token or header_token

    if token is not None:
        if not await _is_valid_access_token(token):
            await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
            return

    await ws_connection_manager.connect(websocket)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        await ws_connection_manager.disconnect(websocket)
    except Exception:
        await ws_connection_manager.disconnect(websocket)

