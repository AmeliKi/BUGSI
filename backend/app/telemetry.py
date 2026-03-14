import logging

from fastapi import FastAPI
from opentelemetry import metrics, trace
from opentelemetry.exporter.otlp.proto.grpc.metric_exporter import OTLPMetricExporter
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.instrumentation.logging import LoggingInstrumentor
from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor

from app.config import settings

logger = logging.getLogger(__name__)

resource = Resource.create(
    {
        "service.name": "bugsi-backend",
        "service.version": "0.1.0",
    }
)

# Custom metrics
meter = metrics.get_meter("bugsi-backend")

login_attempts_counter = meter.create_counter(
    "bugsi.auth.login_attempts",
    description="Number of login attempts",
)

data_ingested_counter = meter.create_counter(
    "bugsi.device_data.ingested",
    description="Number of device data items ingested",
)

ota_deployments_counter = meter.create_counter(
    "bugsi.ota.deployments",
    description="Number of OTA deployment status changes",
)

upload_size_histogram = meter.create_histogram(
    "bugsi.uploads.size_bytes",
    description="Size of uploaded files in bytes",
    unit="By",
)


def setup_telemetry(app: FastAPI) -> None:
    """Configure OpenTelemetry tracing, metrics, and logging instrumentation."""
    endpoint = settings.OTEL_EXPORTER_OTLP_ENDPOINT

    if settings.OTEL_ENABLED:
        # Traces
        tracer_provider = TracerProvider(resource=resource)
        try:
            span_exporter = OTLPSpanExporter(endpoint=endpoint, insecure=True)
            tracer_provider.add_span_processor(BatchSpanProcessor(span_exporter))
        except Exception:
            logger.warning("Could not connect OTLP trace exporter at %s", endpoint)
        trace.set_tracer_provider(tracer_provider)

        # Metrics
        try:
            metric_exporter = OTLPMetricExporter(endpoint=endpoint, insecure=True)
            metric_reader = PeriodicExportingMetricReader(metric_exporter)
            meter_provider = MeterProvider(resource=resource, metric_readers=[metric_reader])
            metrics.set_meter_provider(meter_provider)
        except Exception:
            logger.warning("Could not connect OTLP metric exporter at %s", endpoint)

        logger.info("OpenTelemetry export enabled (endpoint=%s)", endpoint)
    else:
        logger.info("OpenTelemetry export disabled (set OTEL_ENABLED=true to enable)")

    # Auto-instrument FastAPI
    FastAPIInstrumentor.instrument_app(app)

    # Auto-instrument SQLAlchemy
    from app.database import engine

    SQLAlchemyInstrumentor().instrument(engine=engine.sync_engine)

    # Integrate logging with trace context
    LoggingInstrumentor().instrument(set_logging_format=True)
