import io
import json
import tarfile

import pytest

from app.services.ota_package_validator import PackageValidationError, validate_package
from tests.helpers import build_test_package


class TestValidatePackage:
    def test_valid_full_package(self):
        data = build_test_package(version="1.0.0", package_type="full")
        manifest = validate_package(data, "1.0.0", "full")
        assert manifest["package_version"] == "1.0.0"
        assert manifest["package_type"] == "full"
        assert len(manifest["files"]) >= 2

    def test_valid_daemon_only_package(self):
        data = build_test_package(version="2.0.0", package_type="daemon_only")
        manifest = validate_package(data, "2.0.0", "daemon_only")
        assert manifest["package_type"] == "daemon_only"

    def test_valid_config_only_package(self):
        data = build_test_package(version="3.0.0", package_type="config_only")
        manifest = validate_package(data, "3.0.0", "config_only")
        assert manifest["package_type"] == "config_only"

    def test_not_a_tarfile(self):
        with pytest.raises(PackageValidationError, match="not a valid .tar.gz"):
            validate_package(b"not a tar file", "1.0.0", "full")

    def test_missing_manifest(self):
        buf = io.BytesIO()
        with tarfile.open(fileobj=buf, mode="w:gz") as tar:
            data = b"hello"
            info = tarfile.TarInfo(name="root/some_file.txt")
            info.size = len(data)
            tar.addfile(info, io.BytesIO(data))
        with pytest.raises(PackageValidationError, match="manifest.json"):
            validate_package(buf.getvalue(), "1.0.0", "full")

    def test_invalid_json_manifest(self):
        buf = io.BytesIO()
        with tarfile.open(fileobj=buf, mode="w:gz") as tar:
            data = b"not json {"
            info = tarfile.TarInfo(name="root/manifest.json")
            info.size = len(data)
            tar.addfile(info, io.BytesIO(data))
        with pytest.raises(PackageValidationError, match="not valid JSON"):
            validate_package(buf.getvalue(), "1.0.0", "full")

    def test_missing_required_field(self):
        buf = io.BytesIO()
        with tarfile.open(fileobj=buf, mode="w:gz") as tar:
            manifest = json.dumps({"schema_version": 1}).encode()
            info = tarfile.TarInfo(name="root/manifest.json")
            info.size = len(manifest)
            tar.addfile(info, io.BytesIO(manifest))
        with pytest.raises(PackageValidationError, match="missing required field"):
            validate_package(buf.getvalue(), "1.0.0", "full")

    def test_version_mismatch(self):
        data = build_test_package(version="1.0.0", package_type="full")
        with pytest.raises(PackageValidationError, match="does not match"):
            validate_package(data, "2.0.0", "full")

    def test_type_mismatch(self):
        data = build_test_package(version="1.0.0", package_type="full")
        with pytest.raises(PackageValidationError, match="does not match"):
            validate_package(data, "1.0.0", "daemon_only")

    def test_missing_required_directory(self):
        # Build a package with type "full" but only daemon files (missing config/)
        data = build_test_package(
            version="1.0.0",
            package_type="full",
            daemon_files={"daemon/main.py": b"x"},
            config_files={},  # Empty = no config files
        )
        with pytest.raises(PackageValidationError, match="requires 'config/' directory"):
            validate_package(data, "1.0.0", "full")

    def test_unsupported_schema_version(self):
        buf = io.BytesIO()
        with tarfile.open(fileobj=buf, mode="w:gz") as tar:
            manifest = json.dumps({
                "schema_version": 99,
                "package_version": "1.0.0",
                "package_type": "full",
                "target_device": "bugsi-rpi",
                "files": [{"path": "daemon/x.py", "sha256": "abc", "size_bytes": 1}],
            }).encode()
            info = tarfile.TarInfo(name="root/manifest.json")
            info.size = len(manifest)
            tar.addfile(info, io.BytesIO(manifest))
        with pytest.raises(PackageValidationError, match="Unsupported schema_version"):
            validate_package(buf.getvalue(), "1.0.0", "full")

    def test_file_listed_but_missing_in_archive(self):
        """Manifest lists a file that doesn't exist in the archive."""
        import hashlib
        root = "bugsi-update-1.0.0"
        buf = io.BytesIO()
        with tarfile.open(fileobj=buf, mode="w:gz") as tar:
            # Add daemon dir with one file
            content = b"hello"
            finfo = tarfile.TarInfo(name=f"{root}/daemon/main.py")
            finfo.size = len(content)
            tar.addfile(finfo, io.BytesIO(content))

            # Manifest references a file that doesn't exist
            manifest = json.dumps({
                "schema_version": 1,
                "package_version": "1.0.0",
                "package_type": "daemon_only",
                "target_device": "bugsi-rpi",
                "files": [
                    {"path": "daemon/main.py", "sha256": hashlib.sha256(content).hexdigest(), "size_bytes": 5},
                    {"path": "daemon/missing.py", "sha256": "abc", "size_bytes": 1},
                ],
            }).encode()
            minfo = tarfile.TarInfo(name=f"{root}/manifest.json")
            minfo.size = len(manifest)
            tar.addfile(minfo, io.BytesIO(manifest))

        with pytest.raises(PackageValidationError, match="not found in archive"):
            validate_package(buf.getvalue(), "1.0.0", "daemon_only")
