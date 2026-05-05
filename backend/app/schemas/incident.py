from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.models.enums import IncidentType


class IncidentResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    camera_id: int
    type: IncidentType
    timestamp: datetime
    image_path: str


class IncidentCreateRequest(BaseModel):
    camera_id: int = Field(gt=0)
    type: IncidentType
    timestamp: datetime
    image_path: str = Field(min_length=1, max_length=1024)


class IncidentListResponse(BaseModel):
    items: list[IncidentResponse]
    page: int = Field(ge=1)
    page_size: int = Field(ge=1)
    total: int = Field(ge=0)
