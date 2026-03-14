"""Shared test helpers for building valid OTA packages."""

import hashlib
import io
import json
import tarfile
from datetime import datetime, timezone


def build_test_package(
    version: str = "1.0.0",
    package_type: str = "full",
    daemon_files: dict[str, bytes] | None = None,
    config_files: dict[str, bytes] | None = None,
) -> bytes:
    """Build a valid OTA tar.gz package for testing."""
    root_name = f"bugsi-update-{version}"
    manifest_files = []

    if daemon_files is None and package_type in ("full", "daemon_only"):
        daemon_files = {
            "daemon/main.py": f"# BUGSI v{version}\n".encode(),
        }
    if config_files is None and package_type in ("full", "config_only"):
        config_files = {
            "config/device_config.json": json.dumps({"interval": 60}).encode(),
        }

    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as tar:
        all_files = {}
        if daemon_files:
            all_files.update(daemon_files)
        if config_files:
            all_files.update(config_files)

        for rel_path, content in all_files.items():
            info = tarfile.TarInfo(name=f"{root_name}/{rel_path}")
            info.size = len(content)
            tar.addfile(info, io.BytesIO(content))
            manifest_files.append({
                "path": rel_path,
                "sha256": hashlib.sha256(content).hexdigest(),
                "size_bytes": len(content),
            })

        manifest = {
            "schema_version": 1,
            "package_version": version,
            "package_type": package_type,
            "target_device": "bugsi-rpi",
            "created_at": datetime.now(timezone.utc).isoformat(),
            "files": manifest_files,
            "install_instructions": {
                "post_install": "restart_daemon",
                "install_order": ["config", "daemon"],
            },
        }
        manifest_bytes = json.dumps(manifest, indent=2).encode()
        info = tarfile.TarInfo(name=f"{root_name}/manifest.json")
        info.size = len(manifest_bytes)
        tar.addfile(info, io.BytesIO(manifest_bytes))

    return buf.getvalue()
