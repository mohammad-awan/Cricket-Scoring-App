from typing import Literal
from pydantic import BaseModel


class ComponentHealth(BaseModel):
    status: Literal["ok", "error"]
    detail: str


class HealthResponse(BaseModel):
    status: Literal["ok", "degraded"]
    api: ComponentHealth
    database: ComponentHealth