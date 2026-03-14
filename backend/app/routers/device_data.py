import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, File, Form, Request, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import get_db
from app.dependencies import get_device_from_api_key
from app.exceptions import PayloadTooLargeError
from app.rate_limit import limiter
from app.models.device import Device
from app.schemas.telemetry import TelemetryBatchIn, TelemetryReadingOut
from app.schemas.thumbnail import ThumbnailOut
from app.schemas.device_config import ConfigAckRequest, DeviceConfigPollResponse, DeviceConfigPushRequest, DeviceConfigPushResponse
from app.schemas.ota import OtaStatusReport
from app.services import config_service, onboard_service, ota_service, telemetry_service, thumbnail_service
from app.telemetry import data_ingested_counter, upload_size_histogram

router = APIRouter(prefix="/api/device-data", tags=["device-data"])


@router.post("/telemetry", response_model=list[TelemetryReadingOut], status_code=201)
@limiter.limit("100/minute")
async def ingest_telemetry(
    request: Request,
    data: TelemetryBatchIn,
    db: AsyncSession = Depends(get_db),
    device: Device = Depends(get_device_from_api_key),
):
    result = await telemetry_service.ingest_readings(db, device.id, data.readings)
    data_ingested_counter.add(len(data.readings), {"type": "telemetry"})
    return result


@router.post("/thumbnails", response_model=ThumbnailOut, status_code=201)
@limiter.limit("20/minute")
async def upload_thumbnail(
    request: Request,
    image: UploadFile = File(...),
    timestamp: datetime = Form(...),
    db: AsyncSession = Depends(get_db),
    device: Device = Depends(get_device_from_api_key),
):
    image_data = await image.read()
    if len(image_data) > settings.MAX_THUMBNAIL_SIZE_BYTES:
        raise PayloadTooLargeError(
            f"Thumbnail exceeds maximum size of {settings.MAX_THUMBNAIL_SIZE_BYTES // (1024 * 1024)} MB"
        )
    result = await thumbnail_service.save_thumbnail(
        db, device.id, timestamp, image_data
    )
    data_ingested_counter.add(1, {"type": "thumbnails"})
    upload_size_histogram.record(len(image_data), {"type": "thumbnail"})
    return result


@router.get("/config", response_model=DeviceConfigPollResponse)
@limiter.limit("30/minute")
async def poll_config(
    request: Request,
    db: AsyncSession = Depends(get_db),
    device: Device = Depends(get_device_from_api_key),
):
    return await config_service.poll_config(db, device.id)


@router.put("/config", response_model=DeviceConfigPushResponse)
@limiter.limit("10/minute")
async def push_config(
    request: Request,
    data: DeviceConfigPushRequest,
    db: AsyncSession = Depends(get_db),
    device: Device = Depends(get_device_from_api_key),
):
    return await config_service.apply_device_push(db, device.id, data.config, data.version)


@router.post("/config/ack", status_code=204)
@limiter.limit("30/minute")
async def ack_config(
    request: Request,
    data: ConfigAckRequest,
    db: AsyncSession = Depends(get_db),
    device: Device = Depends(get_device_from_api_key),
):
    await config_service.ack_config(db, device.id, data.version)


@router.get("/ota/check")
@limiter.limit("10/minute")
async def check_ota(
    request: Request,
    db: AsyncSession = Depends(get_db),
    device: Device = Depends(get_device_from_api_key),
):
    return await ota_service.check_for_update(db, device.id)


@router.get("/ota/{deployment_id}/download")
@limiter.limit("5/minute")
async def download_ota(
    request: Request,
    deployment_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    device: Device = Depends(get_device_from_api_key),
):
    from fastapi.responses import FileResponse

    file_path = await ota_service.get_package_file_path(db, deployment_id, device.id)
    return FileResponse(file_path, media_type="application/gzip")


@router.post("/ota/{deployment_id}/status", status_code=204)
@limiter.limit("10/minute")
async def report_ota_status(
    request: Request,
    deployment_id: uuid.UUID,
    data: OtaStatusReport,
    db: AsyncSession = Depends(get_db),
    device: Device = Depends(get_device_from_api_key),
):
    await ota_service.update_deployment_status(db, deployment_id, data.status, data.error_message, device.id)


@router.get("/onboard")
@limiter.limit("5/minute")
async def onboard(
    request: Request,
    device: Device = Depends(get_device_from_api_key),
):
    from fastapi.responses import PlainTextResponse

    api_key = request.headers["x-api-key"]
    api_url = f"{request.url.scheme}://{request.url.netloc}/api/device-data"
    script = onboard_service.generate_bootstrap_script(api_key, api_url, device.name)
    return PlainTextResponse(script, media_type="text/x-shellscript")


@router.get("/onboard/bundle")
@limiter.limit("5/minute")
async def onboard_bundle(
    request: Request,
    device: Device = Depends(get_device_from_api_key),
):
    from fastapi.responses import Response

    data = onboard_service.create_bundle_tarball(
        settings.DEVICE_CLIENT_DIR, settings.INSECT_DETECTOR_DIR
    )
    return Response(
        content=data,
        media_type="application/gzip",
        headers={"Content-Disposition": 'attachment; filename="bugsi-bundle.tar.gz"'},
    )
