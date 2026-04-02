from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    DATABASE_URL: str = "postgresql+asyncpg://bugsi:bugsi_dev@localhost:5432/bugsi"
    SECRET_KEY: str  # Required — no default
    UPLOAD_DIR: str = "/data/uploads"
    HEAVY_FILES_DIR: str = "/data/heavy-files"
    CORS_ORIGINS: str = "http://localhost:5173,http://localhost:3000"
    ADMIN_EMAIL: str = "admin@bugsi.local"
    ADMIN_PASSWORD: str  # Required — no default

    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7

    MAX_THUMBNAIL_SIZE_BYTES: int = 5 * 1024 * 1024  # 5 MB
    MAX_OTA_PACKAGE_SIZE_BYTES: int = 500 * 1024 * 1024  # 500 MB

    DB_POOL_SIZE: int = 10
    DB_MAX_OVERFLOW: int = 20
    DB_POOL_TIMEOUT: int = 30

    OTEL_ENABLED: bool = False
    OTEL_EXPORTER_OTLP_ENDPOINT: str = "http://localhost:4317"

    GIT_REPO_URL: str = ""
    GIT_DEVICE_CODE_PATH: str = "device-client/bugsi_daemon"
    GIT_CONFIG_PATH: str = ""

    OTA_SIGNING_KEY_PATH: str = ""
    OTA_SIGNING_PUBLIC_KEY_PATH: str = ""

    DEVICE_CLIENT_DIR: str = "/device-client"
    INSECT_DETECTOR_DIR: str = "/insect-detector"

    GIT_INSECT_DETECTOR_PATH: str = "insect-detector"

    model_config = {"env_file": ".env", "extra": "ignore"}


settings = Settings()
