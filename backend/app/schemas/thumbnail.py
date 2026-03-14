import uuid
from datetime import datetime

from pydantic import BaseModel


class ThumbnailOut(BaseModel):
    id: uuid.UUID
    device_id: uuid.UUID
    timestamp: datetime
    file_path: str
    file_size_bytes: int
    width: int | None
    height: int | None
    created_at: datetime

    model_config = {"from_attributes": True}
