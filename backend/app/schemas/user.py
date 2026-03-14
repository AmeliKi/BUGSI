import uuid
from datetime import datetime

from pydantic import BaseModel


class UserCreate(BaseModel):
    email: str
    password: str
    full_name: str
    role: str = "user"
    language: str = "en"


class UserUpdate(BaseModel):
    email: str | None = None
    full_name: str | None = None
    role: str | None = None
    is_active: bool | None = None
    language: str | None = None


class UserResponse(BaseModel):
    id: uuid.UUID
    email: str
    full_name: str
    role: str
    is_active: bool
    language: str
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class PasswordReset(BaseModel):
    new_password: str


class ChangePassword(BaseModel):
    current_password: str
    new_password: str


class UserDeviceAssignment(BaseModel):
    device_ids: list[uuid.UUID]
