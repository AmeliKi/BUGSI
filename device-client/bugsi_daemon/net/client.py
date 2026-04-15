from __future__ import annotations

import os
import tempfile

import httpx

# Lazy import: OtaInstaller / OtaInstallError are imported inside
# process_ota_update() to avoid pulling in `cryptography` at module load.
# This keeps lightweight commands (config-pull, telemetry, …) working even
# when the cryptography native lib is missing or built for the wrong arch.


class BugsiClient:
    """HTTP client for BUGSI device communication with the backend."""

    def __init__(
        self,
        base_url: str,
        api_key: str,
        timeout: float = 30.0,
        ota_public_key_path: str | None = None,
    ):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.ota_public_key_path = ota_public_key_path
        self.http = httpx.Client(
            base_url=self.base_url,
            headers={"X-API-Key": api_key},
            timeout=timeout,
        )

    def send_telemetry(self, readings: list[dict]) -> list[dict]:
        resp = self.http.post("/telemetry", json={"readings": readings})
        resp.raise_for_status()
        return resp.json()

    def upload_thumbnail(self, image_data: bytes, timestamp: str) -> dict:
        data = {"timestamp": timestamp}
        files = {"image": ("thumbnail.jpg", image_data, "image/jpeg")}
        resp = self.http.post("/thumbnails", data=data, files=files)
        resp.raise_for_status()
        return resp.json()

    def poll_config(self) -> dict:
        resp = self.http.get("/config")
        resp.raise_for_status()
        return resp.json()

    def push_config(self, config: dict, version: int) -> dict:
        """Push locally-edited config to SaaS backend."""
        resp = self.http.put("/config", json={"config": config, "version": version})
        resp.raise_for_status()
        return resp.json()

    def ack_config(self, version: int) -> None:
        resp = self.http.post("/config/ack", json={"version": version})
        resp.raise_for_status()

    def check_ota(self) -> dict:
        resp = self.http.get("/ota/check")
        resp.raise_for_status()
        return resp.json()

    def download_ota(self, deployment_id: str, dest_path: str) -> None:
        resp = self.http.get(f"/ota/{deployment_id}/download")
        resp.raise_for_status()
        with open(dest_path, "wb") as f:
            f.write(resp.content)

    def report_ota_status(
        self, deployment_id: str, status: str, error_message: str | None = None
    ) -> None:
        payload: dict = {"status": status}
        if error_message:
            payload["error_message"] = error_message
        resp = self.http.post(f"/ota/{deployment_id}/status", json=payload)
        resp.raise_for_status()

    def process_ota_update(self, deployment: dict, install_dir: str | None = None) -> dict:
        """Full OTA cycle: download -> verify -> extract -> validate -> apply -> report."""
        deployment_id = deployment["id"]
        expected_checksum = deployment["checksum_sha256"]

        self.report_ota_status(deployment_id, "downloading")

        with tempfile.NamedTemporaryFile(suffix=".tar.gz", delete=False) as tmp:
            tmp_path = tmp.name

        try:
            self.download_ota(deployment_id, tmp_path)
        except Exception as e:
            self.report_ota_status(deployment_id, "failed", f"Download failed: {e}")
            return {"success": False, "install_path": None, "manifest": None, "error": f"Download failed: {e}"}

        from bugsi_daemon.net.ota_installer import OtaInstaller, OtaInstallError

        installer = OtaInstaller(install_base_dir=install_dir)
        try:
            installer.verify_checksum(tmp_path, expected_checksum)
        except OtaInstallError as e:
            self.report_ota_status(deployment_id, "failed", str(e))
            return {"success": False, "install_path": None, "manifest": None, "error": str(e)}

        signature = deployment.get("signature")
        if signature and self.ota_public_key_path:
            try:
                installer.verify_signature(tmp_path, signature, self.ota_public_key_path)
            except OtaInstallError as e:
                self.report_ota_status(deployment_id, "failed", str(e))
                return {"success": False, "install_path": None, "manifest": None, "error": str(e)}

        self.report_ota_status(deployment_id, "installing")

        try:
            manifest = installer.extract_and_validate(tmp_path)
        except OtaInstallError as e:
            self.report_ota_status(deployment_id, "failed", str(e))
            return {"success": False, "install_path": None, "manifest": None, "error": str(e)}

        try:
            install_path = installer.apply()
            installer.cleanup_staging()
        except OtaInstallError as e:
            self.report_ota_status(deployment_id, "failed", str(e))
            return {"success": False, "install_path": None, "manifest": None, "error": str(e)}

        self.report_ota_status(deployment_id, "completed")

        if os.path.exists(tmp_path):
            os.remove(tmp_path)

        return {
            "success": True,
            "install_path": install_path,
            "manifest": manifest,
            "error": None,
        }

    def close(self):
        self.http.close()
