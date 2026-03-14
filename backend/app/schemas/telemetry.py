import uuid
from datetime import datetime

from pydantic import BaseModel


class TelemetryReadingIn(BaseModel):
    timestamp: datetime
    battery_voltage: float | None = None
    battery_soc: float | None = None
    battery_current: float | None = None
    battery_power: float | None = None
    battery_consumed_ah: float | None = None
    battery_ttg_min: int | None = None
    temperature: float | None = None
    humidity: float | None = None
    lte_signal_strength: int | None = None
    lte_signal_quality: int | None = None
    storage_used_mb: int | None = None
    storage_total_mb: int | None = None
    cpu_temp: float | None = None
    uptime_seconds: int | None = None
    pictures_taken: int | None = None


class TelemetryBatchIn(BaseModel):
    readings: list[TelemetryReadingIn]


class TelemetryReadingOut(TelemetryReadingIn):
    id: uuid.UUID
    device_id: uuid.UUID
    created_at: datetime

    model_config = {"from_attributes": True}
