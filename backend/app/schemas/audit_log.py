import json
import uuid
from datetime import datetime

from pydantic import BaseModel, field_validator


class AuditLogResponse(BaseModel):
    id: uuid.UUID
    actor_id: uuid.UUID | None
    actor_email: str | None
    action: str
    resource_type: str
    resource_id: str | None
    details: dict | None
    created_at: datetime

    model_config = {"from_attributes": True}

    @field_validator("details", mode="before")
    @classmethod
    def parse_details(cls, v: str | dict | None) -> dict | None:
        if v is None:
            return None
        if isinstance(v, str):
            return json.loads(v)
        return v
