"""Validates the internal structure of OTA .tar.gz packages."""

import io
import json
import tarfile

VALID_PACKAGE_TYPES = {"full", "daemon_only", "config_only"}
REQUIRED_DIRS_BY_TYPE = {
    "full": {"daemon", "config"},
    "daemon_only": {"daemon"},
    "config_only": {"config"},
}
CURRENT_SCHEMA_VERSION = 1


class PackageValidationError(Exception):
    def __init__(self, message: str):
        self.message = message
        super().__init__(message)


def validate_package(file_data: bytes, expected_version: str, expected_type: str) -> dict:
    """Validate a .tar.gz OTA package. Returns the parsed manifest on success."""
    try:
        fileobj = io.BytesIO(file_data)
        tar = tarfile.open(fileobj=fileobj, mode="r:gz")
    except (tarfile.TarError, Exception):
        raise PackageValidationError("File is not a valid .tar.gz archive")

    members = tar.getnames()

    # Security: reject path traversal
    for name in members:
        if name.startswith("/") or ".." in name:
            tar.close()
            raise PackageValidationError(f"Unsafe path in archive: {name}")

    manifest_path = _find_manifest(members)
    if manifest_path is None:
        tar.close()
        raise PackageValidationError("Package does not contain manifest.json")

    manifest_file = tar.extractfile(manifest_path)
    if manifest_file is None:
        tar.close()
        raise PackageValidationError("Cannot read manifest.json from archive")
    try:
        manifest = json.loads(manifest_file.read())
    except json.JSONDecodeError:
        tar.close()
        raise PackageValidationError("manifest.json is not valid JSON")

    _validate_manifest_fields(manifest)

    if manifest["package_version"] != expected_version:
        tar.close()
        raise PackageValidationError(
            f"Manifest version '{manifest['package_version']}' does not match "
            f"upload version '{expected_version}'"
        )
    if manifest["package_type"] != expected_type:
        tar.close()
        raise PackageValidationError(
            f"Manifest type '{manifest['package_type']}' does not match "
            f"upload type '{expected_type}'"
        )

    root_prefix = manifest_path.rsplit("/", 1)[0] + "/" if "/" in manifest_path else ""
    required_dirs = REQUIRED_DIRS_BY_TYPE.get(expected_type, set())
    for dir_name in required_dirs:
        dir_prefix = root_prefix + dir_name + "/"
        if not any(m.startswith(dir_prefix) for m in members):
            tar.close()
            raise PackageValidationError(
                f"Package type '{expected_type}' requires '{dir_name}/' directory"
            )

    for file_entry in manifest["files"]:
        expected_path = root_prefix + file_entry["path"]
        if expected_path not in members:
            tar.close()
            raise PackageValidationError(
                f"File listed in manifest not found in archive: {file_entry['path']}"
            )

    tar.close()
    return manifest


def _find_manifest(member_names: list[str]) -> str | None:
    for name in member_names:
        if name == "manifest.json" or name.endswith("/manifest.json"):
            parts = name.split("/")
            if len(parts) <= 2:
                return name
    return None


def _validate_manifest_fields(manifest: dict) -> None:
    required = ["schema_version", "package_version", "package_type", "target_device", "files"]
    for field in required:
        if field not in manifest:
            raise PackageValidationError(f"Manifest missing required field: '{field}'")

    if manifest["schema_version"] != CURRENT_SCHEMA_VERSION:
        raise PackageValidationError(
            f"Unsupported schema_version: {manifest['schema_version']}"
        )

    if manifest["package_type"] not in VALID_PACKAGE_TYPES:
        raise PackageValidationError(
            f"Invalid package_type in manifest: '{manifest['package_type']}'"
        )

    if not isinstance(manifest["files"], list) or len(manifest["files"]) == 0:
        raise PackageValidationError("Manifest 'files' must be a non-empty list")

    for i, f in enumerate(manifest["files"]):
        for key in ("path", "sha256", "size_bytes"):
            if key not in f:
                raise PackageValidationError(
                    f"Manifest files[{i}] missing required field: '{key}'"
                )
