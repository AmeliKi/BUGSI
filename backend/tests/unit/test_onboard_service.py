import io
import tarfile

import pytest

from app.exceptions import NotFoundError
from app.services.onboard_service import create_bundle_tarball, generate_bootstrap_script


class TestGenerateBootstrapScript:
    def test_contains_credentials(self):
        script = generate_bootstrap_script("bugsi_test123", "http://server:8000/api/device-data", "My Device")
        assert "bugsi_test123" in script
        assert "http://server:8000/api/device-data" in script
        assert '"api_key": "bugsi_test123"' in script
        assert '"api_url": "http://server:8000/api/device-data"' in script

    def test_is_valid_bash(self):
        script = generate_bootstrap_script("bugsi_key", "http://host/api/device-data", "Dev")
        assert script.startswith("#!/usr/bin/env bash\n")
        assert "set -euo pipefail" in script

    def test_runs_all_steps(self):
        script = generate_bootstrap_script("bugsi_key", "http://host/api/device-data", "Dev")
        assert "install_hardware.sh" in script
        assert "install.sh" in script
        assert "systemctl start bugsi-daemon" in script
        assert "bugsi telemetry" in script
        assert "bugsi upload" in script
        assert "systemctl start bugsi-detector" in script

    def test_includes_detector_step(self):
        script = generate_bootstrap_script("bugsi_key", "http://host/api/device-data", "Dev")
        assert "Step 4/4" in script
        assert "insect-detector" in script

    def test_contains_device_name(self):
        script = generate_bootstrap_script("bugsi_key", "http://host/api/device-data", "Trap Alpha-7")
        assert "Trap Alpha-7" in script


class TestCreateBundleTarball:
    def test_valid_tarball(self, tmp_path):
        (tmp_path / "install.sh").write_text("#!/bin/bash\necho install")
        (tmp_path / "install_hardware.sh").write_text("#!/bin/bash\necho hw")
        (tmp_path / "pyproject.toml").write_text("[project]\nname='bugsi'")
        pkg = tmp_path / "bugsi_daemon"
        pkg.mkdir()
        (pkg / "__init__.py").write_text("")

        data = create_bundle_tarball(str(tmp_path))

        with tarfile.open(fileobj=io.BytesIO(data), mode="r:gz") as tar:
            names = tar.getnames()
        assert any("install.sh" in n for n in names)
        assert any("install_hardware.sh" in n for n in names)
        assert any("pyproject.toml" in n for n in names)
        assert any("bugsi_daemon/__init__.py" in n for n in names)

    def test_excludes_patterns(self, tmp_path):
        (tmp_path / "install.sh").write_text("ok")
        venv = tmp_path / ".venv"
        venv.mkdir()
        (venv / "bin").mkdir()
        pycache = tmp_path / "__pycache__"
        pycache.mkdir()
        (pycache / "mod.cpython-312.pyc").write_text("")
        (tmp_path / "something.pyc").write_text("")

        data = create_bundle_tarball(str(tmp_path))

        with tarfile.open(fileobj=io.BytesIO(data), mode="r:gz") as tar:
            names = tar.getnames()
        assert not any(".venv" in n for n in names)
        assert not any("__pycache__" in n for n in names)
        assert not any(n.endswith(".pyc") for n in names)

    def test_missing_dir_raises(self):
        with pytest.raises(NotFoundError):
            create_bundle_tarball("/nonexistent/path/to/nowhere")

    def test_includes_detector_when_provided(self, tmp_path):
        # Create device-client dir
        client_dir = tmp_path / "device-client"
        client_dir.mkdir()
        (client_dir / "install.sh").write_text("#!/bin/bash\necho install")

        # Create detector dir
        detector_dir = tmp_path / "insect-detector"
        detector_dir.mkdir()
        (detector_dir / "detector.py").write_text("print('detect')")
        config_dir = detector_dir / "config"
        config_dir.mkdir()
        (config_dir / "defaults.json").write_text("{}")

        data = create_bundle_tarball(str(client_dir), str(detector_dir))

        with tarfile.open(fileobj=io.BytesIO(data), mode="r:gz") as tar:
            names = tar.getnames()
        assert any("device-client" in n for n in names)
        assert any("insect-detector" in n for n in names)
        assert any("detector.py" in n for n in names)

    def test_bundle_without_detector(self, tmp_path):
        client_dir = tmp_path / "device-client"
        client_dir.mkdir()
        (client_dir / "install.sh").write_text("#!/bin/bash\necho install")

        data = create_bundle_tarball(str(client_dir))

        with tarfile.open(fileobj=io.BytesIO(data), mode="r:gz") as tar:
            names = tar.getnames()
        assert any("device-client" in n for n in names)
        assert not any("insect-detector" in n for n in names)

    def test_bundle_skips_missing_detector_dir(self, tmp_path):
        client_dir = tmp_path / "device-client"
        client_dir.mkdir()
        (client_dir / "install.sh").write_text("#!/bin/bash\necho install")

        data = create_bundle_tarball(str(client_dir), "/nonexistent/detector")

        with tarfile.open(fileobj=io.BytesIO(data), mode="r:gz") as tar:
            names = tar.getnames()
        assert any("device-client" in n for n in names)
        assert not any("insect-detector" in n for n in names)
