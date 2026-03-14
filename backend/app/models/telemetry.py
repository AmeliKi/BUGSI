import uuid
from datetime import datetime, timezone

from sqlalchemy import DateTime, Float, ForeignKey, Index, Integer
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class TelemetryReading(Base):
    __tablename__ = "telemetry_readings"
    __table_args__ = (Index("ix_telemetry_device_timestamp", "device_id", "timestamp"),)

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    device_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("devices.id"), nullable=False)
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    battery_voltage: Mapped[float | None] = mapped_column(Float, nullable=True)
    battery_soc: Mapped[float | None] = mapped_column(Float, nullable=True)
    battery_current: Mapped[float | None] = mapped_column(Float, nullable=True)
    battery_power: Mapped[float | None] = mapped_column(Float, nullable=True)
    battery_consumed_ah: Mapped[float | None] = mapped_column(Float, nullable=True)
    battery_ttg_min: Mapped[int | None] = mapped_column(Integer, nullable=True)
    temperature: Mapped[float | None] = mapped_column(Float, nullable=True)
    humidity: Mapped[float | None] = mapped_column(Float, nullable=True)
    lte_signal_strength: Mapped[int | None] = mapped_column(Integer, nullable=True)
    lte_signal_quality: Mapped[int | None] = mapped_column(Integer, nullable=True)
    storage_used_mb: Mapped[int | None] = mapped_column(Integer, nullable=True)
    storage_total_mb: Mapped[int | None] = mapped_column(Integer, nullable=True)
    cpu_temp: Mapped[float | None] = mapped_column(Float, nullable=True)
    uptime_seconds: Mapped[int | None] = mapped_column(Integer, nullable=True)
    pictures_taken: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc)
    )

    device = relationship("Device", back_populates="telemetry_readings")
