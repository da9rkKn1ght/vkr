from pydantic import BaseModel, ConfigDict, Field, field_validator


class ZoneBase(BaseModel):
    camera_id: int = Field(gt=0)
    coordinates: list[list[float]]

    @field_validator("coordinates")
    @classmethod
    def validate_coordinates(cls, coordinates: list[list[float]]) -> list[list[float]]:
        if not coordinates:
            raise ValueError("Coordinates must contain at least one point")

        normalized: list[list[float]] = []
        for point in coordinates:
            if len(point) != 2:
                raise ValueError("Each coordinate must be an array of [x, y]")

            x, y = point
            normalized.append([float(x), float(y)])

        return normalized


class ZoneCreate(ZoneBase):
    pass


class ZoneUpdate(BaseModel):
    camera_id: int | None = Field(default=None, gt=0)
    coordinates: list[list[float]] | None = None

    @field_validator("coordinates")
    @classmethod
    def validate_coordinates(cls, coordinates: list[list[float]] | None) -> list[list[float]] | None:
        if coordinates is None:
            return None
        if not coordinates:
            raise ValueError("Coordinates must contain at least one point")

        normalized: list[list[float]] = []
        for point in coordinates:
            if len(point) != 2:
                raise ValueError("Each coordinate must be an array of [x, y]")
            x, y = point
            normalized.append([float(x), float(y)])

        return normalized


class ZoneResponse(ZoneBase):
    model_config = ConfigDict(from_attributes=True)

    id: int

