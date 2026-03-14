"""OTA package installer for BUGSI devices.

Handles: download -> verify -> extract -> validate -> apply -> report.
"""

import base64
import hashlib
import json
import os
import shutil
import tarfile
import tempfile

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec


class OtaInstallError(Exception):
    pass


class OtaInstaller:
    """Processes downloaded OTA packages."""

    def __init__(self, install_base_dir: str | None = None):
        self.install_base_dir = install_base_dir or tempfile.mkdtemp(prefix="bugsi_ota_")
        self._manifest = None
        self._package_root = None
        self._staging_dir = None

    @property
    def manifest(self) -> dict | None:
        return self._manifest

    def verify_signature(
        self, file_path: str, signature_b64: str, public_key_path: str
    ) -> None:
        """Verify ECDSA P-256 signature of a file. Raises OtaInstallError on failure."""
        with open(public_key_path, "rb") as f:
            public_key = serialization.load_pem_public_key(f.read())

        if not isinstance(public_key, ec.EllipticCurvePublicKey):
            raise OtaInstallError("Verification key must be an ECDSA public key")

        with open(file_path, "rb") as f:
            file_data = f.read()

        try:
            signature = base64.b64decode(signature_b64)
            public_key.verify(signature, file_data, ec.ECDSA(hashes.SHA256()))
        except Exception as e:
            raise OtaInstallError(f"Signature verification failed: {e}")

    def verify_checksum(self, file_path: str, expected_sha256: str) -> None:
        actual = self._file_sha256(file_path)
        if actual != expected_sha256:
            raise OtaInstallError(
                f"Checksum mismatch: expected {expected_sha256}, got {actual}"
            )

    def extract_and_validate(self, tar_gz_path: str) -> dict:
        """Extract the tar.gz and validate its manifest. Returns the parsed manifest."""
        staging_dir = os.path.join(self.install_base_dir, "_staging")
        os.makedirs(staging_dir, exist_ok=True)

        try:
            with tarfile.open(tar_gz_path, "r:gz") as tar:
                for member in tar.getmembers():
                    if member.name.startswith("/") or ".." in member.name:
                        raise OtaInstallError(f"Unsafe path in archive: {member.name}")
                tar.extractall(path=staging_dir, filter="data")
        except tarfile.TarError as e:
            raise OtaInstallError(f"Failed to extract package: {e}")

        manifest_path = self._find_manifest(staging_dir)
        if manifest_path is None:
            raise OtaInstallError("Package does not contain manifest.json")

        with open(manifest_path) as f:
            try:
                manifest = json.load(f)
            except json.JSONDecodeError as e:
                raise OtaInstallError(f"Invalid manifest.json: {e}")

        package_root = os.path.dirname(manifest_path)

        for field in ("schema_version", "package_version", "package_type", "files"):
            if field not in manifest:
                raise OtaInstallError(f"Manifest missing field: {field}")

        for file_entry in manifest["files"]:
            file_abs_path = os.path.join(package_root, file_entry["path"])
            if not os.path.exists(file_abs_path):
                raise OtaInstallError(
                    f"File listed in manifest not found: {file_entry['path']}"
                )
            actual_sha256 = self._file_sha256(file_abs_path)
            if actual_sha256 != file_entry["sha256"]:
                raise OtaInstallError(
                    f"Checksum mismatch for {file_entry['path']}: "
                    f"expected {file_entry['sha256']}, got {actual_sha256}"
                )
            actual_size = os.path.getsize(file_abs_path)
            if actual_size != file_entry["size_bytes"]:
                raise OtaInstallError(
                    f"Size mismatch for {file_entry['path']}: "
                    f"expected {file_entry['size_bytes']}, got {actual_size}"
                )

        self._manifest = manifest
        self._package_root = package_root
        self._staging_dir = staging_dir
        return manifest

    def apply(self) -> str:
        """Apply the validated package to the install directory. Returns install path."""
        if self._manifest is None:
            raise OtaInstallError("Must call extract_and_validate() first")

        install_dir = os.path.join(
            self.install_base_dir,
            f"v{self._manifest['package_version']}",
        )
        os.makedirs(install_dir, exist_ok=True)

        install_order = (
            self._manifest
            .get("install_instructions", {})
            .get("install_order", ["config", "daemon"])
        )

        for component in install_order:
            src = os.path.join(self._package_root, component)
            if os.path.isdir(src):
                dst = os.path.join(install_dir, component)
                shutil.copytree(src, dst, dirs_exist_ok=True)

        for file_entry in self._manifest["files"]:
            src = os.path.join(self._package_root, file_entry["path"])
            dst = os.path.join(install_dir, file_entry["path"])
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            if not os.path.exists(dst):
                shutil.copy2(src, dst)

        return install_dir

    def cleanup_staging(self) -> None:
        if self._staging_dir and os.path.exists(self._staging_dir):
            shutil.rmtree(self._staging_dir)

    @staticmethod
    def _find_manifest(base_dir: str) -> str | None:
        for entry in os.listdir(base_dir):
            entry_path = os.path.join(base_dir, entry)
            if entry == "manifest.json" and os.path.isfile(entry_path):
                return entry_path
            if os.path.isdir(entry_path):
                candidate = os.path.join(entry_path, "manifest.json")
                if os.path.isfile(candidate):
                    return candidate
        return None

    @staticmethod
    def _file_sha256(path: str) -> str:
        sha256 = hashlib.sha256()
        with open(path, "rb") as f:
            for chunk in iter(lambda: f.read(8192), b""):
                sha256.update(chunk)
        return sha256.hexdigest()
