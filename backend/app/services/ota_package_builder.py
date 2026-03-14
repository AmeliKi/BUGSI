"""Builds OTA .tar.gz packages from a git repository commit."""

import base64
import hashlib
import io
import json
import os
import re
import shutil
import subprocess
import tarfile
import tempfile
from datetime import datetime, timezone

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec

_COMMIT_ID_RE = re.compile(r"^[0-9a-f]{6,40}$")


class PackageBuildError(Exception):
    def __init__(self, message: str):
        self.message = message
        super().__init__(message)


def _file_sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _add_file_to_tar(tar: tarfile.TarFile, root: str, rel_path: str, data: bytes) -> None:
    info = tarfile.TarInfo(name=f"{root}/{rel_path}")
    info.size = len(data)
    tar.addfile(info, io.BytesIO(data))


def _collect_files(base_dir: str, prefix: str) -> dict[str, bytes]:
    """Collect all files under base_dir, returning {prefix/relative_path: content}."""
    files = {}
    for dirpath, _dirnames, filenames in os.walk(base_dir):
        for filename in filenames:
            abs_path = os.path.join(dirpath, filename)
            rel_path = os.path.relpath(abs_path, base_dir)
            key = f"{prefix}/{rel_path}"
            with open(abs_path, "rb") as f:
                files[key] = f.read()
    return files


def build_package_from_git(
    repo_url: str,
    commit_id: str,
    package_type: str,
    device_code_path: str,
    config_path: str = "",
    detector_code_path: str = "",
    description: str | None = None,
    version: str | None = None,
) -> tuple[bytes, dict]:
    """
    Clone a git repo at a specific commit and build an OTA package.

    Returns (tar_gz_bytes, manifest_dict).
    """
    if not repo_url:
        raise PackageBuildError("GIT_REPO_URL is not configured")

    if not _COMMIT_ID_RE.match(commit_id):
        raise PackageBuildError("Invalid commit_id format: must be 6-40 lowercase hex characters")

    resolved_version = version or commit_id[:7]
    tmp_dir = tempfile.mkdtemp(prefix="bugsi_ota_build_")

    try:
        clone_dir = os.path.join(tmp_dir, "repo")
        _clone_and_checkout(repo_url, commit_id, clone_dir)

        # Collect daemon files
        daemon_files: dict[str, bytes] = {}
        if package_type in ("full", "daemon_only"):
            daemon_src = os.path.join(clone_dir, device_code_path)
            if not os.path.isdir(daemon_src):
                raise PackageBuildError(
                    f"Device code path '{device_code_path}' not found in repository"
                )
            daemon_files = _collect_files(daemon_src, "daemon")

        # Collect config files
        config_files: dict[str, bytes] = {}
        if package_type in ("full", "config_only") and config_path:
            config_src = os.path.join(clone_dir, config_path)
            if os.path.isdir(config_src):
                config_files = _collect_files(config_src, "config")

        # Collect detector files
        detector_files: dict[str, bytes] = {}
        if package_type in ("full", "detector_only") and detector_code_path:
            detector_src = os.path.join(clone_dir, detector_code_path)
            if os.path.isdir(detector_src):
                detector_files = _collect_files(detector_src, "detector")
            elif package_type == "detector_only":
                raise PackageBuildError(
                    f"Detector code path '{detector_code_path}' not found in repository"
                )

        if not daemon_files and not config_files and not detector_files:
            raise PackageBuildError("No files found to package")

        # Build the tar.gz
        tar_bytes, manifest = _build_tar_gz(
            version=resolved_version,
            package_type=package_type,
            commit_id=commit_id,
            description=description,
            daemon_files=daemon_files,
            config_files=config_files,
            detector_files=detector_files,
        )

        return tar_bytes, manifest

    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


def _clone_and_checkout(repo_url: str, commit_id: str, dest: str) -> None:
    """Clone the repo and checkout the specified commit."""
    try:
        subprocess.run(
            ["git", "clone", "--no-checkout", repo_url, dest],
            check=True,
            capture_output=True,
            timeout=120,
        )
        subprocess.run(
            ["git", "checkout", "--", commit_id],
            cwd=dest,
            check=True,
            capture_output=True,
            timeout=30,
        )
    except subprocess.CalledProcessError as e:
        stderr = e.stderr.decode() if e.stderr else str(e)
        raise PackageBuildError(f"Git operation failed: {stderr}")
    except subprocess.TimeoutExpired:
        raise PackageBuildError("Git operation timed out")


def _build_tar_gz(
    version: str,
    package_type: str,
    commit_id: str,
    description: str | None,
    daemon_files: dict[str, bytes],
    config_files: dict[str, bytes],
    detector_files: dict[str, bytes] | None = None,
) -> tuple[bytes, dict]:
    """Build the tar.gz archive with manifest."""
    root_name = f"bugsi-update-{version}"
    manifest_files = []

    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as tar:
        all_files = {**daemon_files, **config_files, **(detector_files or {})}
        for rel_path, content in sorted(all_files.items()):
            _add_file_to_tar(tar, root_name, rel_path, content)
            manifest_files.append({
                "path": rel_path,
                "sha256": _file_sha256(content),
                "size_bytes": len(content),
            })

        install_order = ["config", "daemon"]
        if detector_files:
            install_order.append("detector")

        manifest = {
            "schema_version": 1,
            "package_version": version,
            "package_type": package_type,
            "target_device": "bugsi-rpi",
            "commit_id": commit_id,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "description": description or f"Built from commit {commit_id[:7]}",
            "files": manifest_files,
            "install_instructions": {
                "post_install": "restart_daemon",
                "install_order": install_order,
            },
        }
        manifest_bytes = json.dumps(manifest, indent=2).encode()
        _add_file_to_tar(tar, root_name, "manifest.json", manifest_bytes)

    return buf.getvalue(), manifest


def sign_package(file_data: bytes, private_key_path: str) -> str:
    """Sign file_data with an ECDSA P-256 private key and return base64-encoded signature."""
    with open(private_key_path, "rb") as f:
        private_key = serialization.load_pem_private_key(f.read(), password=None)

    if not isinstance(private_key, ec.EllipticCurvePrivateKey):
        raise PackageBuildError("Signing key must be an ECDSA private key")

    signature = private_key.sign(file_data, ec.ECDSA(hashes.SHA256()))
    return base64.b64encode(signature).decode("ascii")


def verify_package_signature(
    file_data: bytes, signature_b64: str, public_key_path: str
) -> None:
    """Verify an ECDSA P-256 signature against file_data. Raises PackageBuildError on failure."""
    with open(public_key_path, "rb") as f:
        public_key = serialization.load_pem_public_key(f.read())

    if not isinstance(public_key, ec.EllipticCurvePublicKey):
        raise PackageBuildError("Verification key must be an ECDSA public key")

    try:
        signature = base64.b64decode(signature_b64)
        public_key.verify(signature, file_data, ec.ECDSA(hashes.SHA256()))
    except Exception as e:
        raise PackageBuildError(f"Signature verification failed: {e}")
