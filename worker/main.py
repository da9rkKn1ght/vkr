from __future__ import annotations

import logging
import os
import threading
import time
import uuid
from collections import defaultdict, deque
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import cv2
import httpx
import numpy as np
from dotenv import load_dotenv
from ultralytics import YOLO


COCO_NOSE = 0
COCO_LEFT_SHOULDER = 5
COCO_RIGHT_SHOULDER = 6
COCO_LEFT_WRIST = 9
COCO_RIGHT_WRIST = 10

PHONE_LABEL_ALIASES = {"phone", "cell phone", "cellphone", "mobile phone", "smartphone"}
SMOKING_LABEL_KEYWORDS = ("smoke", "smoking", "cigarette", "vape", "e-cigarette")

INCIDENT_ABSENCE = "absence"
INCIDENT_SLEEP = "sleep"
INCIDENT_PHONE = "phone"
INCIDENT_SMOKING = "smoking"
INCIDENT_ANOMALOUS = "anomalous_movement"

LOGGER = logging.getLogger("ml_worker")


@dataclass(slots=True)
class WorkerSettings:
    backend_api_url: str
    worker_username: str | None
    worker_password: str | None
    worker_token: str | None
    model_path: str
    model_fallback_path: str | None
    tracker_config: str
    absence_threshold_sec: float
    sleep_threshold_sec: float
    object_threshold_sec: float
    anomalous_threshold_sec: float
    speed_limit_px_per_sec: float
    speed_window_frames: int
    immobility_epsilon_px: float
    sleep_posture_ratio: float
    wrist_activity_threshold: float
    object_proximity_px: float
    phone_class_ids: set[int]
    smoking_class_ids: set[int]
    track_stale_sec: float
    incident_cooldown_sec: float
    conf_threshold: float
    iou_threshold: float
    reconnect_delay_sec: float
    max_reconnect_backoff_sec: float
    max_fps: float
    http_timeout_sec: float
    dev_fallback_source: str | None
    dev_fallback_camera_id: int
    uploads_dir: Path

    @classmethod
    def from_env(cls) -> WorkerSettings:
        load_dotenv()
        repo_root = Path(__file__).resolve().parents[1]
        default_uploads = repo_root / "backend" / "uploads" / "incidents"

        def _as_float(name: str, default: float) -> float:
            raw = os.getenv(name, str(default))
            return float(raw)

        def _as_int(name: str, default: int) -> int:
            raw = os.getenv(name, str(default))
            return int(raw)

        def _as_optional(name: str) -> str | None:
            value = os.getenv(name, "").strip()
            return value or None

        def _as_int_set(name: str, default: str) -> set[int]:
            raw = os.getenv(name, default).strip()
            if not raw:
                return set()
            values: set[int] = set()
            for chunk in raw.split(","):
                chunk = chunk.strip()
                if not chunk:
                    continue
                try:
                    values.add(int(chunk))
                except ValueError:
                    LOGGER.warning("Invalid class id '%s' in %s, ignored", chunk, name)
            return values

        return cls(
            backend_api_url=os.getenv("BACKEND_API_URL", "http://localhost:8000/api/v1").rstrip("/"),
            worker_username=_as_optional("WORKER_USERNAME"),
            worker_password=_as_optional("WORKER_PASSWORD"),
            worker_token=_as_optional("WORKER_TOKEN"),
            model_path=os.getenv("MODEL_PATH", "models/yolov26_custom.pt"),
            model_fallback_path=_as_optional("MODEL_FALLBACK_PATH"),
            tracker_config=os.getenv("TRACKER_CONFIG", "botsort.yaml"),
            absence_threshold_sec=_as_float("ABSENCE_THRESHOLD_SEC", 10.0),
            sleep_threshold_sec=_as_float("SLEEP_THRESHOLD_SEC", 15.0),
            object_threshold_sec=_as_float("OBJECT_THRESHOLD_SEC", 3.0),
            anomalous_threshold_sec=_as_float("ANOMALOUS_THRESHOLD_SEC", 2.0),
            speed_limit_px_per_sec=_as_float("SPEED_LIMIT_PX_PER_SEC", 140.0),
            speed_window_frames=max(2, _as_int("SPEED_WINDOW_FRAMES", 5)),
            immobility_epsilon_px=_as_float("IMMOBILITY_EPSILON_PX", 8.0),
            sleep_posture_ratio=_as_float("SLEEP_POSTURE_RATIO", 0.65),
            wrist_activity_threshold=_as_float("WRIST_ACTIVITY_THRESHOLD", 15.0),
            object_proximity_px=max(0.0, _as_float("OBJECT_PROXIMITY_PX", 12.0)),
            phone_class_ids=_as_int_set("PHONE_CLASS_IDS", "67"),
            smoking_class_ids=_as_int_set("SMOKING_CLASS_IDS", ""),
            track_stale_sec=_as_float("TRACK_STALE_SEC", 4.0),
            incident_cooldown_sec=_as_float("INCIDENT_COOLDOWN_SEC", 10.0),
            conf_threshold=_as_float("CONF_THRESHOLD", 0.25),
            iou_threshold=_as_float("IOU_THRESHOLD", 0.45),
            reconnect_delay_sec=max(0.5, _as_float("RECONNECT_DELAY_SEC", 3.0)),
            max_reconnect_backoff_sec=max(1.0, _as_float("MAX_RECONNECT_BACKOFF_SEC", 30.0)),
            max_fps=max(0.0, _as_float("MAX_FPS", 12.0)),
            http_timeout_sec=max(2.0, _as_float("HTTP_TIMEOUT_SEC", 10.0)),
            dev_fallback_source=_as_optional("DEV_FALLBACK_SOURCE"),
            dev_fallback_camera_id=_as_int("DEV_FALLBACK_CAMERA_ID", 1),
            uploads_dir=Path(os.getenv("UPLOADS_DIR", str(default_uploads))),
        )


@dataclass(slots=True)
class CameraConfig:
    camera_id: int
    name: str
    source: str
    zones: list[np.ndarray]


@dataclass(slots=True)
class TrackedPersonState:
    last_seen_ts: float = 0.0
    last_centroid: tuple[float, float] | None = None
    last_centroid_ts: float | None = None
    centroid_speed_px_per_sec: float | None = None
    speed_samples: deque[float] = field(default_factory=lambda: deque(maxlen=8))
    anomalous_started_ts: float | None = None
    prev_pose_points: np.ndarray | None = None
    prev_wrists: np.ndarray | None = None
    wrist_activity_samples: deque[float] = field(default_factory=lambda: deque(maxlen=8))
    baseline_nose_shoulder_dist: float | None = None
    sleep_started_ts: float | None = None
    object_contact_started_ts: dict[str, float] = field(default_factory=dict)
    last_incident_ts: dict[str, float] = field(default_factory=dict)


class BackendApiClient:
    def __init__(self, settings: WorkerSettings) -> None:
        self._settings = settings
        self._client = httpx.Client(timeout=settings.http_timeout_sec)
        self._token: str | None = settings.worker_token
        self._lock = threading.Lock()

    def close(self) -> None:
        self._client.close()

    def _authorization_header(self) -> dict[str, str]:
        with self._lock:
            token = self._token
        if token:
            return {"Authorization": f"Bearer {token}"}
        return {}

    def _login(self) -> bool:
        if not self._settings.worker_username or not self._settings.worker_password:
            return False

        login_url = f"{self._settings.backend_api_url}/auth/login"
        try:
            response = self._client.post(
                login_url,
                json={
                    "username": self._settings.worker_username,
                    "password": self._settings.worker_password,
                },
            )
            response.raise_for_status()
        except httpx.HTTPError as exc:
            LOGGER.error("Worker login failed: %s", exc)
            return False

        token = response.json().get("access_token")
        if not token:
            LOGGER.error("Worker login response does not contain access_token")
            return False

        with self._lock:
            self._token = token
        return True

    def _request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        json_payload: dict[str, Any] | None = None,
        auth_required: bool = False,
        allow_reauth: bool = True,
    ) -> httpx.Response | None:
        if auth_required and not self._token and not self._login():
            LOGGER.error("Cannot perform authenticated request %s %s: auth unavailable", method, path)
            return None

        url = f"{self._settings.backend_api_url}{path}"
        headers = self._authorization_header() if auth_required else {}
        try:
            response = self._client.request(method, url, params=params, json=json_payload, headers=headers)
        except httpx.HTTPError as exc:
            LOGGER.error("HTTP request failed %s %s: %s", method, path, exc)
            return None

        if response.status_code == 401 and auth_required and allow_reauth:
            if self._login():
                return self._request(
                    method,
                    path,
                    params=params,
                    json_payload=json_payload,
                    auth_required=auth_required,
                    allow_reauth=False,
                )

        return response

    def fetch_active_cameras(self) -> list[dict[str, Any]]:
        response = self._request("GET", "/cameras", auth_required=True)
        if response is None:
            return []
        if response.status_code != 200:
            LOGGER.error("Failed to fetch cameras: %s %s", response.status_code, response.text)
            return []

        cameras = response.json()
        return [camera for camera in cameras if camera.get("is_active", False)]

    def fetch_zones(self) -> list[dict[str, Any]]:
        response = self._request("GET", "/zones", auth_required=True)
        if response is None:
            return []
        if response.status_code != 200:
            LOGGER.error("Failed to fetch zones: %s %s", response.status_code, response.text)
            return []
        return response.json()

    def post_incident(self, payload: dict[str, Any]) -> bool:
        response = self._request("POST", "/incidents", json_payload=payload, auth_required=False)
        if response is None:
            return False
        if response.status_code not in (200, 201):
            LOGGER.error(
                "Failed to POST incident camera_id=%s type=%s: %s %s",
                payload.get("camera_id"),
                payload.get("type"),
                response.status_code,
                response.text,
            )
            return False
        return True


def parse_source(source: str) -> str | int:
    cleaned = source.strip()
    if cleaned.isdigit():
        return int(cleaned)
    return cleaned


def bbox_center(xyxy: tuple[float, float, float, float]) -> tuple[float, float]:
    x1, y1, x2, y2 = xyxy
    return ((x1 + x2) / 2.0, (y1 + y2) / 2.0)


def point_in_or_near_rect(point: tuple[float, float], rect: tuple[float, float, float, float], margin: float) -> bool:
    x, y = point
    x1, y1, x2, y2 = rect
    return (x1 - margin) <= x <= (x2 + margin) and (y1 - margin) <= y <= (y2 + margin)


def boxes_overlap_or_near(
    box_a: tuple[float, float, float, float],
    box_b: tuple[float, float, float, float],
    margin: float,
) -> bool:
    ax1, ay1, ax2, ay2 = box_a
    bx1, by1, bx2, by2 = box_b
    return (ax1 - margin) <= bx2 and (bx1 - margin) <= ax2 and (ay1 - margin) <= by2 and (by1 - margin) <= ay2


def euclidean_distance(p1: tuple[float, float], p2: tuple[float, float]) -> float:
    return float(np.hypot(p1[0] - p2[0], p1[1] - p2[1]))


class CameraProcessor(threading.Thread):
    def __init__(
        self,
        *,
        camera: CameraConfig,
        settings: WorkerSettings,
        backend_client: BackendApiClient,
        stop_event: threading.Event,
    ) -> None:
        super().__init__(name=f"camera-{camera.camera_id}", daemon=True)
        self._camera = camera
        self._settings = settings
        self._backend_client = backend_client
        self._stop_event = stop_event

        self._person_states: dict[int, TrackedPersonState] = {}
        self._camera_last_incident_ts: dict[str, float] = {}
        self._absence_started_ts: float | None = None
        self._absence_fired: bool = False
        self._fallback_roi_polygon: np.ndarray | None = None
        self._fallback_roi_frame_shape: tuple[int, int] | None = None
        self._video_frame_dt_sec: float | None = None
        self._last_video_ts_sec: float | None = None
        self._source_is_local_mp4 = self._is_local_mp4_source(self._camera.source)
        self._active_source_is_local_mp4 = self._source_is_local_mp4
        self._model = self._load_model()

    @staticmethod
    def _is_local_mp4_source(source: str) -> bool:
        cleaned = source.strip().lower().split("?", 1)[0]
        if not cleaned.endswith(".mp4"):
            return False
        for prefix in ("rtsp://", "rtmp://", "http://", "https://"):
            if cleaned.startswith(prefix):
                return False
        return True

    def _load_model(self) -> YOLO:
        try:
            LOGGER.info(
                "Camera %s (%s): loading model '%s'",
                self._camera.camera_id,
                self._camera.name,
                self._settings.model_path,
            )
            return YOLO(self._settings.model_path)
        except Exception as exc:
            if not self._settings.model_fallback_path:
                raise RuntimeError(f"Cannot load model '{self._settings.model_path}'") from exc

            LOGGER.warning(
                "Camera %s (%s): failed loading model '%s', fallback to '%s'. Error: %s",
                self._camera.camera_id,
                self._camera.name,
                self._settings.model_path,
                self._settings.model_fallback_path,
                exc,
            )
            return YOLO(self._settings.model_fallback_path)

    def run(self) -> None:
        LOGGER.info(
            "Camera %s (%s): processing started, source=%s",
            self._camera.camera_id,
            self._camera.name,
            self._camera.source,
        )
        reconnect_attempt = 0

        while not self._stop_event.is_set():
            capture: cv2.VideoCapture | None = None
            try:
                capture = self._open_capture_with_fallback(self._camera.source)
                if capture is None:
                    reconnect_attempt += 1
                    delay = self._reconnect_delay(reconnect_attempt)
                    LOGGER.warning(
                        "Camera %s (%s): stream open failed, retry in %.1fs (attempt=%s)",
                        self._camera.camera_id,
                        self._camera.name,
                        delay,
                        reconnect_attempt,
                    )
                    time.sleep(delay)
                    continue

                reconnect_attempt = 0
                stream_stopped_by_drop = self._capture_loop(capture)
                if self._stop_event.is_set():
                    break

                if stream_stopped_by_drop:
                    reconnect_attempt += 1
                    delay = self._reconnect_delay(reconnect_attempt)
                    LOGGER.warning(
                        "Camera %s (%s): stream disconnected, retry in %.1fs (attempt=%s)",
                        self._camera.camera_id,
                        self._camera.name,
                        delay,
                        reconnect_attempt,
                    )
                    time.sleep(delay)
            except Exception as exc:
                reconnect_attempt += 1
                delay = self._reconnect_delay(reconnect_attempt)
                LOGGER.exception(
                    "Camera %s (%s): loop error '%s', retry in %.1fs (attempt=%s)",
                    self._camera.camera_id,
                    self._camera.name,
                    exc,
                    delay,
                    reconnect_attempt,
                )
                time.sleep(delay)
            finally:
                if capture is not None:
                    capture.release()

    def _reconnect_delay(self, attempt: int) -> float:
        multiplier = 2 ** max(0, attempt - 1)
        delay = self._settings.reconnect_delay_sec * multiplier
        return min(delay, self._settings.max_reconnect_backoff_sec)

    def _open_capture_with_fallback(self, source: str) -> cv2.VideoCapture | None:
        primary = cv2.VideoCapture(parse_source(source))
        if primary.isOpened():
            self._active_source_is_local_mp4 = self._is_local_mp4_source(source)
            self._configure_video_timing(primary)
            return primary
        primary.release()

        if self._settings.dev_fallback_source:
            fallback = cv2.VideoCapture(parse_source(self._settings.dev_fallback_source))
            if fallback.isOpened():
                self._active_source_is_local_mp4 = self._is_local_mp4_source(self._settings.dev_fallback_source)
                self._configure_video_timing(fallback)
                LOGGER.warning(
                    "Camera %s (%s): primary source unavailable, using fallback source=%s",
                    self._camera.camera_id,
                    self._camera.name,
                    self._settings.dev_fallback_source,
                )
                return fallback
            fallback.release()

        LOGGER.error(
            "Camera %s (%s): failed to open source '%s'",
            self._camera.camera_id,
            self._camera.name,
            source,
        )
        self._video_frame_dt_sec = None
        self._last_video_ts_sec = None
        return None

    def _configure_video_timing(self, capture: cv2.VideoCapture) -> None:
        self._last_video_ts_sec = None
        if not self._active_source_is_local_mp4:
            self._video_frame_dt_sec = None
            return

        fps = float(capture.get(cv2.CAP_PROP_FPS) or 0.0)
        if fps > 0:
            self._video_frame_dt_sec = 1.0 / fps
            LOGGER.info(
                "Camera %s (%s): local mp4 timing enabled fps=%.3f dt=%.6f",
                self._camera.camera_id,
                self._camera.name,
                fps,
                self._video_frame_dt_sec,
            )
            return

        self._video_frame_dt_sec = None
        LOGGER.warning(
            "Camera %s (%s): local mp4 has invalid FPS, fallback to synthetic dt from frame timestamps",
            self._camera.camera_id,
            self._camera.name,
        )

    def _resolve_frame_timestamp(self, capture: cv2.VideoCapture, fallback_monotonic: float) -> float:
        if not self._active_source_is_local_mp4:
            return fallback_monotonic

        timestamp_sec = float(capture.get(cv2.CAP_PROP_POS_MSEC) or 0.0) / 1000.0
        if timestamp_sec <= 0 and self._video_frame_dt_sec is not None:
            frame_pos = float(capture.get(cv2.CAP_PROP_POS_FRAMES) or 0.0)
            if frame_pos > 0:
                timestamp_sec = max(0.0, (frame_pos - 1.0) * self._video_frame_dt_sec)

        if timestamp_sec <= 0 and self._video_frame_dt_sec is not None:
            if self._last_video_ts_sec is None:
                timestamp_sec = 0.0
            else:
                timestamp_sec = self._last_video_ts_sec + self._video_frame_dt_sec
        elif timestamp_sec <= 0:
            timestamp_sec = fallback_monotonic

        if self._last_video_ts_sec is not None and timestamp_sec <= self._last_video_ts_sec:
            if self._video_frame_dt_sec is not None:
                timestamp_sec = self._last_video_ts_sec + self._video_frame_dt_sec
            else:
                timestamp_sec = self._last_video_ts_sec + 1e-3

        self._last_video_ts_sec = timestamp_sec
        return timestamp_sec

    def _capture_loop(self, capture: cv2.VideoCapture) -> bool:
        last_frame_ts = 0.0
        while not self._stop_event.is_set():
            ok, frame = capture.read()
            if not ok or frame is None:
                if self._active_source_is_local_mp4 and capture.isOpened():
                    rewound = capture.set(cv2.CAP_PROP_POS_FRAMES, 0)
                    if rewound:
                        ok, frame = capture.read()
                        if ok and frame is not None:
                            LOGGER.info(
                                "Camera %s (%s): loop local mp4 source from frame 0",
                                self._camera.camera_id,
                                self._camera.name,
                            )
                        else:
                            LOGGER.warning(
                                "Camera %s (%s): mp4 rewind succeeded but next read failed",
                                self._camera.camera_id,
                                self._camera.name,
                            )
                            return True
                    else:
                        LOGGER.warning(
                            "Camera %s (%s): failed to rewind local mp4 source",
                            self._camera.camera_id,
                            self._camera.name,
                        )
                        return True
                else:
                    return True

            if frame is None:
                return True

            wall_clock_now = time.monotonic()
            if self._settings.max_fps > 0:
                min_interval = 1.0 / self._settings.max_fps
                if wall_clock_now - last_frame_ts < min_interval:
                    continue
                last_frame_ts = wall_clock_now

            now = self._resolve_frame_timestamp(capture, wall_clock_now)

            try:
                self._process_frame(frame, now)
            except Exception as exc:
                LOGGER.exception(
                    "Camera %s (%s): frame processing error: %s",
                    self._camera.camera_id,
                    self._camera.name,
                    exc,
                )
        return False

    def _process_frame(self, frame: np.ndarray, now_monotonic: float) -> None:
        effective_zones = self._get_effective_zones(frame)
        results = self._model.track(
            source=frame,
            persist=True,
            tracker=self._settings.tracker_config,
            conf=self._settings.conf_threshold,
            iou=self._settings.iou_threshold,
            verbose=False,
        )
        if not results:
            self._handle_absence([], frame, now_monotonic)
            return

        result = results[0]
        incident_frame = self._plot_result_frame(result, frame)
        persons, phone_boxes, smoking_boxes = self._extract_entities(result, effective_zones)
        # Absence is computed strictly by ROI inclusion of the person's centroid.
        tracked_persons = [
            person
            for person in persons
            if person["track_id"] is not None and self._inside_roi(person["centroid"], effective_zones)
        ]
        self._handle_absence(tracked_persons, incident_frame, now_monotonic)

        active_track_ids: set[int] = set()
        for person in persons:
            # Even if the detector keeps a track, outside-ROI centroids are ignored for discipline logic.
            if not self._inside_roi(person["centroid"], effective_zones):
                continue

            track_id = person["track_id"]
            if track_id is None:
                continue

            state = self._person_states.setdefault(
                track_id,
                TrackedPersonState(
                    speed_samples=deque(maxlen=self._settings.speed_window_frames),
                    wrist_activity_samples=deque(maxlen=self._settings.speed_window_frames),
                ),
            )
            active_track_ids.add(track_id)
            state.last_seen_ts = now_monotonic

            centroid = person["centroid"]
            keypoints = person["keypoints"]

            self._update_anomalous_movement(
                frame=incident_frame,
                person_state=state,
                track_id=track_id,
                centroid=centroid,
                now_monotonic=now_monotonic,
            )
            self._update_sleep_state(
                frame=incident_frame,
                person_state=state,
                track_id=track_id,
                keypoints=keypoints,
                now_monotonic=now_monotonic,
            )
            self._update_object_state(
                frame=incident_frame,
                person_state=state,
                track_id=track_id,
                person_bbox=person["bbox"],
                keypoints=keypoints,
                object_boxes=phone_boxes,
                object_type=INCIDENT_PHONE,
                now_monotonic=now_monotonic,
            )
            self._update_object_state(
                frame=incident_frame,
                person_state=state,
                track_id=track_id,
                person_bbox=person["bbox"],
                keypoints=keypoints,
                object_boxes=smoking_boxes,
                object_type=INCIDENT_SMOKING,
                now_monotonic=now_monotonic,
            )

        self._prune_stale_tracks(active_track_ids, now_monotonic)

    def _extract_entities(
        self,
        result: Any,
        zones: list[np.ndarray],
    ) -> tuple[list[dict[str, Any]], list[tuple[float, float, float, float]], list[tuple[float, float, float, float]]]:
        persons: list[dict[str, Any]] = []
        phone_boxes: list[tuple[float, float, float, float]] = []
        smoking_boxes: list[tuple[float, float, float, float]] = []

        if result.boxes is None or len(result.boxes) == 0:
            return persons, phone_boxes, smoking_boxes

        boxes_xyxy = result.boxes.xyxy.detach().cpu().numpy()
        boxes_cls = result.boxes.cls.detach().cpu().numpy().astype(int)
        track_ids: np.ndarray | None = None
        if result.boxes.id is not None:
            track_ids = result.boxes.id.detach().cpu().numpy().astype(int)

        keypoints_xy: np.ndarray | None = None
        if getattr(result, "keypoints", None) is not None and result.keypoints.xy is not None:
            keypoints_xy = result.keypoints.xy.detach().cpu().numpy()

        model_names = result.names if hasattr(result, "names") else {}

        for idx, xyxy_array in enumerate(boxes_xyxy):
            x1, y1, x2, y2 = map(float, xyxy_array.tolist())
            bbox = (x1, y1, x2, y2)
            center = bbox_center(bbox)
            if not self._inside_roi(center, zones):
                continue

            cls_id = int(boxes_cls[idx])
            raw_label = self._resolve_class_name(model_names, cls_id)
            normalized_label = self._normalize_label(raw_label, cls_id)

            if normalized_label == "person":
                track_id: int | None = int(track_ids[idx]) if track_ids is not None else None
                person_keypoints = keypoints_xy[idx] if keypoints_xy is not None and idx < len(keypoints_xy) else None
                persons.append(
                    {
                        "track_id": track_id,
                        "bbox": bbox,
                        "centroid": center,
                        "keypoints": person_keypoints,
                    }
                )
            elif normalized_label == INCIDENT_PHONE:
                phone_boxes.append(bbox)
            elif normalized_label == INCIDENT_SMOKING:
                smoking_boxes.append(bbox)

        return persons, phone_boxes, smoking_boxes

    @staticmethod
    def _inside_roi(point: tuple[float, float], zones: list[np.ndarray]) -> bool:
        if not zones:
            return True
        px, py = point
        for polygon in zones:
            if cv2.pointPolygonTest(polygon, (px, py), False) >= 0:
                return True
        return False

    def _get_effective_zones(self, frame: np.ndarray) -> list[np.ndarray]:
        if self._camera.zones:
            return self._camera.zones

        height, width = frame.shape[:2]
        frame_shape = (width, height)
        if self._fallback_roi_polygon is None or self._fallback_roi_frame_shape != frame_shape:
            polygon = np.array(
                [
                    [0.0, 0.0],
                    [float(width - 1), 0.0],
                    [float(width - 1), float(height - 1)],
                    [0.0, float(height - 1)],
                ],
                dtype=np.float32,
            ).reshape((-1, 1, 2))
            self._fallback_roi_polygon = polygon
            self._fallback_roi_frame_shape = frame_shape
            LOGGER.debug(
                "Camera %s (%s): no ROI zones configured, fallback to full frame %sx%s",
                self._camera.camera_id,
                self._camera.name,
                width,
                height,
            )
        return [self._fallback_roi_polygon]

    def _plot_result_frame(self, result: Any, frame: np.ndarray) -> np.ndarray:
        try:
            plotted = result.plot()
            if isinstance(plotted, np.ndarray):
                return plotted
        except Exception as exc:
            LOGGER.debug("Camera %s (%s): result.plot() failed: %s", self._camera.camera_id, self._camera.name, exc)
        return frame

    def _normalize_label(self, raw_label: str, cls_id: int) -> str | None:
        label = raw_label.strip().lower()
        if label == "person" or cls_id == 0:
            return "person"
        if label in PHONE_LABEL_ALIASES or cls_id in self._settings.phone_class_ids:
            return INCIDENT_PHONE
        if any(keyword in label for keyword in SMOKING_LABEL_KEYWORDS) or cls_id in self._settings.smoking_class_ids:
            return INCIDENT_SMOKING
        return None

    @staticmethod
    def _resolve_class_name(model_names: Any, cls_id: int) -> str:
        if isinstance(model_names, dict):
            return str(model_names.get(cls_id, cls_id)).lower()
        if isinstance(model_names, list) and 0 <= cls_id < len(model_names):
            return str(model_names[cls_id]).lower()
        return str(cls_id).lower()

    def _handle_absence(self, persons: list[dict[str, Any]], frame: np.ndarray, now_monotonic: float) -> None:
        if persons:
            self._absence_started_ts = None
            self._absence_fired = False
            return

        if self._absence_started_ts is None:
            self._absence_started_ts = now_monotonic
            return

        absent_duration = now_monotonic - self._absence_started_ts
        if absent_duration >= self._settings.absence_threshold_sec and not self._absence_fired:
            if self._can_emit_camera_level(INCIDENT_ABSENCE, now_monotonic):
                self._emit_incident(frame=frame, incident_type=INCIDENT_ABSENCE, track_id=None)
                self._mark_camera_incident(INCIDENT_ABSENCE, now_monotonic)
                self._absence_fired = True

    def _update_anomalous_movement(
        self,
        *,
        frame: np.ndarray,
        person_state: TrackedPersonState,
        track_id: int,
        centroid: tuple[float, float],
        now_monotonic: float,
    ) -> None:
        if person_state.last_centroid is not None and person_state.last_centroid_ts is not None:
            dt = now_monotonic - person_state.last_centroid_ts
            if dt > 0:
                dx = centroid[0] - person_state.last_centroid[0]
                dy = centroid[1] - person_state.last_centroid[1]
                speed = float(np.sqrt(dx * dx + dy * dy) / dt)
                person_state.speed_samples.append(speed)
                avg_speed = float(np.mean(person_state.speed_samples))
                person_state.centroid_speed_px_per_sec = avg_speed
                LOGGER.debug(
                    "Track %s | Speed=%.2f px/s | AvgSpeed=%.2f px/s | Samples=%s | dt=%.3f",
                    track_id,
                    speed,
                    avg_speed,
                    len(person_state.speed_samples),
                    dt,
                )
                LOGGER.debug(
                    "Camera %s track=%s speed_debug avg_speed=%.2f speed_limit=%.2f",
                    self._camera.camera_id,
                    track_id,
                    avg_speed,
                    self._settings.speed_limit_px_per_sec,
                )

                if avg_speed > self._settings.speed_limit_px_per_sec:
                    if person_state.anomalous_started_ts is None:
                        person_state.anomalous_started_ts = now_monotonic
                    elif now_monotonic - person_state.anomalous_started_ts >= self._settings.anomalous_threshold_sec:
                        if self._can_emit(person_state, INCIDENT_ANOMALOUS, now_monotonic) and self._can_emit_camera_level(
                            INCIDENT_ANOMALOUS, now_monotonic
                        ):
                            self._emit_incident(
                                frame=frame,
                                incident_type=INCIDENT_ANOMALOUS,
                                track_id=track_id,
                            )
                            person_state.last_incident_ts[INCIDENT_ANOMALOUS] = now_monotonic
                            self._mark_camera_incident(INCIDENT_ANOMALOUS, now_monotonic)
                        person_state.anomalous_started_ts = None
                        person_state.speed_samples.clear()
                else:
                    person_state.anomalous_started_ts = None
            else:
                person_state.centroid_speed_px_per_sec = None

        person_state.last_centroid = centroid
        person_state.last_centroid_ts = now_monotonic

    def _update_sleep_state(
        self,
        *,
        frame: np.ndarray,
        person_state: TrackedPersonState,
        track_id: int,
        keypoints: np.ndarray | None,
        now_monotonic: float,
    ) -> None:
        pose_points = self._select_pose_points(keypoints, [COCO_NOSE, COCO_LEFT_SHOULDER, COCO_RIGHT_SHOULDER])
        wrists = self._select_pose_points(keypoints, [COCO_LEFT_WRIST, COCO_RIGHT_WRIST], min_points=2)
        nose_to_shoulder = self._nose_to_shoulder_vertical_distance(keypoints)

        if pose_points is None or wrists is None or nose_to_shoulder is None:
            person_state.prev_pose_points = None
            person_state.prev_wrists = None
            person_state.wrist_activity_samples.clear()
            person_state.sleep_started_ts = None
            return

        if person_state.prev_pose_points is None or person_state.prev_pose_points.shape != pose_points.shape:
            person_state.prev_pose_points = pose_points
            person_state.prev_wrists = wrists
            if person_state.baseline_nose_shoulder_dist is None:
                person_state.baseline_nose_shoulder_dist = nose_to_shoulder
            person_state.sleep_started_ts = None
            person_state.wrist_activity_samples.clear()
            return

        prev_wrists = person_state.prev_wrists
        if prev_wrists is None or prev_wrists.shape != wrists.shape:
            prev_wrists = wrists

        wrist_shift = float(np.linalg.norm(wrists - prev_wrists, axis=1).sum())
        person_state.wrist_activity_samples.append(wrist_shift)
        avg_wrist_activity = float(np.mean(person_state.wrist_activity_samples)) if person_state.wrist_activity_samples else 0.0
        if person_state.baseline_nose_shoulder_dist is None:
            person_state.baseline_nose_shoulder_dist = nose_to_shoulder

        baseline = max(person_state.baseline_nose_shoulder_dist or 1.0, 1.0)
        posture_ratio = nose_to_shoulder / baseline if baseline > 0 else 1.0
        head_down = posture_ratio < self._settings.sleep_posture_ratio
        centroid_speed = person_state.centroid_speed_px_per_sec
        body_immobile = centroid_speed is not None and centroid_speed < self._settings.immobility_epsilon_px
        hands_inactive = avg_wrist_activity < self._settings.wrist_activity_threshold
        sleep_candidate = head_down and body_immobile and hands_inactive

        LOGGER.debug(
            "Track %s | NoseShoulderDist=%.2f | Baseline=%.2f | PostureRatio=%.2f | CentroidSpeed=%.2f | AvgWristActivity=%.2f | HeadDown=%s | BodyImmobile=%s | HandsInactive=%s",
            track_id,
            nose_to_shoulder,
            baseline,
            posture_ratio,
            centroid_speed if centroid_speed is not None else -1.0,
            avg_wrist_activity,
            head_down,
            body_immobile,
            hands_inactive,
        )

        if sleep_candidate:
            if person_state.sleep_started_ts is None:
                person_state.sleep_started_ts = now_monotonic
            elif now_monotonic - person_state.sleep_started_ts >= self._settings.sleep_threshold_sec:
                if self._can_emit(person_state, INCIDENT_SLEEP, now_monotonic) and self._can_emit_camera_level(
                    INCIDENT_SLEEP, now_monotonic
                ):
                    self._emit_incident(frame=frame, incident_type=INCIDENT_SLEEP, track_id=track_id)
                    person_state.last_incident_ts[INCIDENT_SLEEP] = now_monotonic
                    self._mark_camera_incident(INCIDENT_SLEEP, now_monotonic)
                person_state.sleep_started_ts = None
        else:
            person_state.sleep_started_ts = None
            if not head_down:
                person_state.baseline_nose_shoulder_dist = (baseline * 0.95) + (nose_to_shoulder * 0.05)

        person_state.prev_pose_points = pose_points
        person_state.prev_wrists = wrists

    def _update_object_state(
        self,
        *,
        frame: np.ndarray,
        person_state: TrackedPersonState,
        track_id: int,
        person_bbox: tuple[float, float, float, float],
        keypoints: np.ndarray | None,
        object_boxes: list[tuple[float, float, float, float]],
        object_type: str,
        now_monotonic: float,
    ) -> None:
        wrists = self._select_pose_points(keypoints, [COCO_LEFT_WRIST, COCO_RIGHT_WRIST], min_points=1)
        if not object_boxes:
            person_state.object_contact_started_ts.pop(object_type, None)
            return

        contact_detected = False
        if wrists is not None:
            for wrist in wrists:
                wrist_point = (float(wrist[0]), float(wrist[1]))
                if any(point_in_or_near_rect(wrist_point, obj_box, self._settings.object_proximity_px) for obj_box in object_boxes):
                    contact_detected = True
                    break
        else:
            # Fallback for distant CCTV: use object-person bbox proximity when wrist keypoints are absent.
            contact_detected = any(
                boxes_overlap_or_near(person_bbox, obj_box, self._settings.object_proximity_px) for obj_box in object_boxes
            )

        if not contact_detected:
            person_state.object_contact_started_ts.pop(object_type, None)
            return

        started_ts = person_state.object_contact_started_ts.get(object_type)
        if started_ts is None:
            person_state.object_contact_started_ts[object_type] = now_monotonic
            return

        if now_monotonic - started_ts >= self._settings.object_threshold_sec:
            if self._can_emit(person_state, object_type, now_monotonic) and self._can_emit_camera_level(
                object_type, now_monotonic
            ):
                self._emit_incident(frame=frame, incident_type=object_type, track_id=track_id)
                person_state.last_incident_ts[object_type] = now_monotonic
                self._mark_camera_incident(object_type, now_monotonic)
            person_state.object_contact_started_ts.pop(object_type, None)

    @staticmethod
    def _select_pose_points(
        keypoints: np.ndarray | None,
        indices: list[int],
        *,
        min_points: int = 2,
    ) -> np.ndarray | None:
        if keypoints is None:
            return None
        if len(keypoints.shape) != 2 or keypoints.shape[1] < 2:
            return None

        points: list[np.ndarray] = []
        for idx in indices:
            if idx >= len(keypoints):
                continue
            x, y = keypoints[idx][:2]
            if x <= 0 and y <= 0:
                continue
            points.append(np.array([float(x), float(y)], dtype=np.float32))

        if len(points) < min_points:
            return None
        return np.stack(points)

    @staticmethod
    def _nose_to_shoulder_vertical_distance(keypoints: np.ndarray | None) -> float | None:
        selected = CameraProcessor._select_pose_points(
            keypoints,
            [COCO_NOSE, COCO_LEFT_SHOULDER, COCO_RIGHT_SHOULDER],
            min_points=3,
        )
        if selected is None or len(selected) < 3:
            return None

        nose_y = float(selected[0][1])
        shoulder_mid_y = float((selected[1][1] + selected[2][1]) / 2.0)
        return abs(nose_y - shoulder_mid_y)

    def _can_emit(self, person_state: TrackedPersonState, incident_type: str, now_monotonic: float) -> bool:
        last_ts = person_state.last_incident_ts.get(incident_type)
        if last_ts is None:
            return True
        return (now_monotonic - last_ts) >= self._settings.incident_cooldown_sec

    def _can_emit_camera_level(self, incident_type: str, now_monotonic: float) -> bool:
        last_ts = self._camera_last_incident_ts.get(incident_type)
        if last_ts is None:
            return True
        return (now_monotonic - last_ts) >= self._settings.incident_cooldown_sec

    def _mark_camera_incident(self, incident_type: str, now_monotonic: float) -> None:
        self._camera_last_incident_ts[incident_type] = now_monotonic

    def _prune_stale_tracks(self, active_track_ids: set[int], now_monotonic: float) -> None:
        to_remove: list[int] = []
        for track_id, state in self._person_states.items():
            if track_id in active_track_ids:
                continue
            if now_monotonic - state.last_seen_ts > self._settings.track_stale_sec:
                to_remove.append(track_id)

        for track_id in to_remove:
            self._person_states.pop(track_id, None)

    def _emit_incident(self, *, frame: np.ndarray, incident_type: str, track_id: int | None) -> None:
        event_ts = datetime.now(timezone.utc)
        self._settings.uploads_dir.mkdir(parents=True, exist_ok=True)

        track_suffix = f"_t{track_id}" if track_id is not None else ""
        filename = (
            f"camera_{self._camera.camera_id}_{incident_type}{track_suffix}_"
            f"{event_ts.strftime('%Y%m%dT%H%M%S')}_{uuid.uuid4().hex[:8]}.jpg"
        )
        disk_path = self._settings.uploads_dir / filename
        relative_image_path = f"/uploads/incidents/{filename}"

        if not cv2.imwrite(str(disk_path), frame):
            LOGGER.error(
                "Camera %s (%s): failed to write incident frame %s",
                self._camera.camera_id,
                self._camera.name,
                disk_path,
            )
            return

        payload = {
            "camera_id": self._camera.camera_id,
            "type": incident_type,
            "timestamp": event_ts.isoformat().replace("+00:00", "Z"),
            "image_path": relative_image_path,
        }
        if self._backend_client.post_incident(payload):
            LOGGER.info(
                "Camera %s (%s): incident sent type=%s track_id=%s image=%s",
                self._camera.camera_id,
                self._camera.name,
                incident_type,
                track_id,
                relative_image_path,
            )


def build_camera_configs(settings: WorkerSettings, backend_client: BackendApiClient) -> list[CameraConfig]:
    cameras = backend_client.fetch_active_cameras()
    zones = backend_client.fetch_zones()

    zones_by_camera: dict[int, list[np.ndarray]] = defaultdict(list)
    for zone in zones:
        camera_id = int(zone.get("camera_id", 0))
        coords = zone.get("coordinates", [])
        if not isinstance(coords, list) or len(coords) < 3:
            continue
        polygon_points = np.array(coords, dtype=np.float32).reshape((-1, 1, 2))
        zones_by_camera[camera_id].append(polygon_points)

    camera_configs: list[CameraConfig] = []
    for camera in cameras:
        camera_id = int(camera["id"])
        source = str(camera.get("rtsp_url", "")).strip()
        if not source and settings.dev_fallback_source:
            source = settings.dev_fallback_source
        if not source:
            LOGGER.warning("Skipping camera id=%s due to empty rtsp_url", camera_id)
            continue

        camera_configs.append(
            CameraConfig(
                camera_id=camera_id,
                name=str(camera.get("name", f"camera-{camera_id}")),
                source=source,
                zones=zones_by_camera.get(camera_id, []),
            )
        )

    if camera_configs:
        return camera_configs

    if settings.dev_fallback_source:
        LOGGER.warning(
            "No active cameras from backend, running in dev fallback mode source=%s camera_id=%s",
            settings.dev_fallback_source,
            settings.dev_fallback_camera_id,
        )
        return [
            CameraConfig(
                camera_id=settings.dev_fallback_camera_id,
                name="dev-fallback-camera",
                source=settings.dev_fallback_source,
                zones=[],
            )
        ]

    return []


def configure_logging() -> None:
    load_dotenv()
    log_level_name = os.getenv("LOG_LEVEL", "INFO").upper()
    log_level = getattr(logging, log_level_name, logging.INFO)
    logging.basicConfig(
        level=log_level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        force=True,
    )
    LOGGER.setLevel(log_level)


def main() -> int:
    configure_logging()
    settings = WorkerSettings.from_env()
    settings.uploads_dir.mkdir(parents=True, exist_ok=True)

    backend_client = BackendApiClient(settings)
    stop_event = threading.Event()

    workers: list[CameraProcessor] = []

    try:
        camera_configs = build_camera_configs(settings, backend_client)
        if not camera_configs:
            LOGGER.error("No camera sources available. Worker stopped.")
            return 1

        workers = [
            CameraProcessor(
                camera=camera_config,
                settings=settings,
                backend_client=backend_client,
                stop_event=stop_event,
            )
            for camera_config in camera_configs
        ]
        for worker in workers:
            worker.start()

        while True:
            time.sleep(1.0)
    except KeyboardInterrupt:
        LOGGER.info("KeyboardInterrupt received, shutting down worker...")
    finally:
        stop_event.set()
        for worker in workers:
            worker.join(timeout=5.0)
        backend_client.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
