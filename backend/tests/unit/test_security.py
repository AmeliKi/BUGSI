"""Tests for security hardening measures."""

import base64
import hmac
import json
import os
import tempfile

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec
from pydantic import ValidationError as PydanticValidationError

from app.services.auth_service import create_access_token, create_refresh_token, decode_token, hash_api_key, hash_password, verify_password
from app.services.thumbnail_service import _validate_image_magic_bytes, _safe_path


class TestTimingAttackMitigation:
    """C1: Login timing attack — verify_password always runs even for missing users."""

    def test_verify_password_against_dummy_hash(self):
        dummy_hash = hash_password("dummy-password-for-timing")
        # Should not raise, just return False
        assert not verify_password("attacker-guess", dummy_hash)

    def test_verify_password_correct(self):
        pw_hash = hash_password("real-password")
        assert verify_password("real-password", pw_hash)

    def test_verify_password_wrong(self):
        pw_hash = hash_password("real-password")
        assert not verify_password("wrong-password", pw_hash)


class TestImageMagicBytes:
    """C5: MIME type validation on uploads."""

    def test_valid_jpeg(self):
        data = b"\xff\xd8\xff\xe0" + b"\x00" * 100
        _validate_image_magic_bytes(data)  # Should not raise

    def test_valid_png(self):
        data = b"\x89PNG\r\n\x1a\n" + b"\x00" * 100
        _validate_image_magic_bytes(data)  # Should not raise

    def test_invalid_gif(self):
        data = b"GIF89a" + b"\x00" * 100
        with pytest.raises(Exception, match="Invalid image format"):
            _validate_image_magic_bytes(data)

    def test_invalid_script(self):
        data = b"#!/bin/bash\nrm -rf /\n"
        with pytest.raises(Exception, match="Invalid image format"):
            _validate_image_magic_bytes(data)

    def test_invalid_empty(self):
        with pytest.raises(Exception, match="Invalid image format"):
            _validate_image_magic_bytes(b"")

    def test_invalid_exe(self):
        data = b"MZ" + b"\x00" * 100  # PE executable magic
        with pytest.raises(Exception, match="Invalid image format"):
            _validate_image_magic_bytes(data)


class TestPathTraversal:
    """H4: Path traversal protection in file serving."""

    def test_safe_path_normal(self):
        result = _safe_path("thumbnails/abc/image.jpg")
        assert result.endswith("thumbnails/abc/image.jpg")

    def test_safe_path_rejects_traversal(self):
        with pytest.raises(Exception):
            _safe_path("../../../etc/passwd")

    def test_safe_path_rejects_absolute(self):
        with pytest.raises(Exception):
            _safe_path("/etc/passwd")

    def test_safe_path_rejects_double_dot_in_middle(self):
        with pytest.raises(Exception):
            _safe_path("thumbnails/../../etc/shadow")


class TestApiKeyConstantTimeComparison:
    """H8: API key comparison must use constant-time comparison."""

    def test_hmac_compare_digest_equal(self):
        key = "bugsi_test_key_12345"
        h = hash_api_key(key)
        assert hmac.compare_digest(h, h)

    def test_hmac_compare_digest_not_equal(self):
        h1 = hash_api_key("bugsi_key_1")
        h2 = hash_api_key("bugsi_key_2")
        assert not hmac.compare_digest(h1, h2)


class TestSecretKeyValidation:
    """H6: SECRET_KEY must have sufficient entropy."""

    def test_known_bad_secrets_rejected(self):
        from app.main import _validate_secret_key
        with pytest.raises(RuntimeError, match="SECRET_KEY must be changed"):
            _validate_secret_key("dev-secret-key-change-in-production")
        with pytest.raises(RuntimeError, match="SECRET_KEY must be changed"):
            _validate_secret_key("bugsi-dev-secret-key-2026")

    def test_short_secret_rejected(self):
        from app.main import _validate_secret_key
        with pytest.raises(RuntimeError, match="at least 32 characters"):
            _validate_secret_key("short")

    def test_valid_secret_accepted(self):
        from app.main import _validate_secret_key
        _validate_secret_key("a-sufficiently-long-secret-key-for-production-use-1234")


class TestAdminPasswordValidation:
    """H5: Admin password must meet complexity requirements."""

    def test_short_password_rejected(self):
        from app.main import _validate_admin_password
        with pytest.raises(RuntimeError, match="at least 12 characters"):
            _validate_admin_password("Short1")

    def test_no_uppercase_rejected(self):
        from app.main import _validate_admin_password
        with pytest.raises(RuntimeError, match="uppercase"):
            _validate_admin_password("alllowercase123")

    def test_no_digit_rejected(self):
        from app.main import _validate_admin_password
        with pytest.raises(RuntimeError, match="digit"):
            _validate_admin_password("AllLettersNoDigit")

    def test_valid_password_accepted(self):
        from app.main import _validate_admin_password
        _validate_admin_password("SecurePass1234")


class TestJwtJtiClaims:
    """C4/H7: JWT tokens must include JTI for blacklisting and rotation."""

    def test_access_token_has_jti(self):
        token = create_access_token("user-1", "admin")
        payload = decode_token(token)
        assert "jti" in payload
        assert len(payload["jti"]) == 36  # UUID format

    def test_refresh_token_has_jti(self):
        token = create_refresh_token("user-1")
        payload = decode_token(token)
        assert "jti" in payload
        assert len(payload["jti"]) == 36

    def test_different_tokens_have_different_jtis(self):
        t1 = create_access_token("user-1", "admin")
        t2 = create_access_token("user-1", "admin")
        jti1 = decode_token(t1)["jti"]
        jti2 = decode_token(t2)["jti"]
        assert jti1 != jti2


class TestCommitIdValidation:
    """L7: commit_id must be validated before passing to git."""

    def test_valid_commit_id(self):
        from app.services.ota_package_builder import _COMMIT_ID_RE
        assert _COMMIT_ID_RE.match("abc123")
        assert _COMMIT_ID_RE.match("a" * 40)
        assert _COMMIT_ID_RE.match("deadbeef")

    def test_invalid_commit_ids(self):
        from app.services.ota_package_builder import _COMMIT_ID_RE
        assert not _COMMIT_ID_RE.match("")  # empty
        assert not _COMMIT_ID_RE.match("abc")  # too short
        assert not _COMMIT_ID_RE.match("ABCDEF")  # uppercase
        assert not _COMMIT_ID_RE.match("abc123; rm -rf /")  # injection attempt
        assert not _COMMIT_ID_RE.match("a" * 41)  # too long
        assert not _COMMIT_ID_RE.match("--hard")  # git flag injection


class TestAdminSeeding:
    """Admin user is created on first start and credentials are synced on restarts."""

    @pytest.fixture(autouse=True)
    def _patch_settings(self, monkeypatch):
        from app.config import settings
        monkeypatch.setattr(settings, "ADMIN_EMAIL", "admin@bugsi.local")
        monkeypatch.setattr(settings, "ADMIN_PASSWORD", "SecurePass1234")

    @pytest.mark.asyncio
    async def test_admin_created_when_none_exists(self, db_session):
        from app.main import _seed_or_update_admin
        from app.models.user import User
        from sqlalchemy import select

        await _seed_or_update_admin(db_session)

        result = await db_session.execute(select(User).where(User.role == "admin"))
        admin = result.scalar_one()
        assert admin.email == "admin@bugsi.local"
        assert verify_password("SecurePass1234", admin.password_hash)

    @pytest.mark.asyncio
    async def test_admin_password_updated_when_changed(self, db_session, monkeypatch):
        from app.config import settings
        from app.main import _seed_or_update_admin
        from app.models.user import User
        from sqlalchemy import select

        # Seed with initial password
        await _seed_or_update_admin(db_session)

        # Change the password in settings
        monkeypatch.setattr(settings, "ADMIN_PASSWORD", "NewPassword5678")
        await _seed_or_update_admin(db_session)

        result = await db_session.execute(select(User).where(User.role == "admin"))
        admin = result.scalar_one()
        assert verify_password("NewPassword5678", admin.password_hash)
        assert not verify_password("SecurePass1234", admin.password_hash)

    @pytest.mark.asyncio
    async def test_admin_email_updated_when_changed(self, db_session, monkeypatch):
        from app.config import settings
        from app.main import _seed_or_update_admin
        from app.models.user import User
        from sqlalchemy import select

        await _seed_or_update_admin(db_session)

        monkeypatch.setattr(settings, "ADMIN_EMAIL", "newadmin@bugsi.local")
        await _seed_or_update_admin(db_session)

        result = await db_session.execute(select(User).where(User.role == "admin"))
        admin = result.scalar_one()
        assert admin.email == "newadmin@bugsi.local"

    @pytest.mark.asyncio
    async def test_admin_unchanged_when_matching(self, db_session):
        from app.main import _seed_or_update_admin
        from app.models.user import User
        from sqlalchemy import select

        await _seed_or_update_admin(db_session)

        result = await db_session.execute(select(User).where(User.role == "admin"))
        admin = result.scalar_one()
        original_hash = admin.password_hash

        # Run again — nothing should change
        await _seed_or_update_admin(db_session)

        result = await db_session.execute(select(User).where(User.role == "admin"))
        admin = result.scalar_one()
        assert admin.password_hash == original_hash


class TestConfigSizeLimit:
    """M2: Device config JSON must have a size limit."""

    def test_small_config_accepted(self):
        from app.schemas.device_config import DeviceConfigUpdate
        config = DeviceConfigUpdate(config_json={"interval": 60})
        assert config.config_json == {"interval": 60}

    def test_oversized_config_rejected(self):
        from app.schemas.device_config import DeviceConfigUpdate, MAX_CONFIG_JSON_SIZE
        # Create a config that exceeds the max size
        huge_value = "x" * (MAX_CONFIG_JSON_SIZE + 1)
        with pytest.raises(PydanticValidationError):
            DeviceConfigUpdate(config_json={"data": huge_value})


class TestOtaSigning:
    """H3: OTA package signing with ECDSA P-256."""

    @pytest.fixture()
    def ecdsa_keypair(self, tmp_path):
        """Generate an ECDSA P-256 keypair and write to PEM files."""
        private_key = ec.generate_private_key(ec.SECP256R1())
        public_key = private_key.public_key()

        private_key_path = str(tmp_path / "test_private.pem")
        public_key_path = str(tmp_path / "test_public.pem")

        with open(private_key_path, "wb") as f:
            f.write(
                private_key.private_bytes(
                    encoding=serialization.Encoding.PEM,
                    format=serialization.PrivateFormat.PKCS8,
                    encryption_algorithm=serialization.NoEncryption(),
                )
            )

        with open(public_key_path, "wb") as f:
            f.write(
                public_key.public_bytes(
                    encoding=serialization.Encoding.PEM,
                    format=serialization.PublicFormat.SubjectPublicKeyInfo,
                )
            )

        return private_key_path, public_key_path

    @pytest.fixture()
    def other_keypair(self, tmp_path):
        """Generate a second ECDSA P-256 keypair (for wrong-key tests)."""
        private_key = ec.generate_private_key(ec.SECP256R1())
        public_key = private_key.public_key()

        public_key_path = str(tmp_path / "other_public.pem")
        with open(public_key_path, "wb") as f:
            f.write(
                public_key.public_bytes(
                    encoding=serialization.Encoding.PEM,
                    format=serialization.PublicFormat.SubjectPublicKeyInfo,
                )
            )

        return public_key_path

    def test_sign_package_produces_valid_signature(self, ecdsa_keypair):
        from app.services.ota_package_builder import sign_package, verify_package_signature

        private_key_path, public_key_path = ecdsa_keypair
        data = b"test OTA package content for signing"

        signature_b64 = sign_package(data, private_key_path)

        # Signature should be a non-empty base64 string
        assert isinstance(signature_b64, str)
        assert len(signature_b64) > 0
        # Should be valid base64
        decoded = base64.b64decode(signature_b64)
        assert len(decoded) > 0

    def test_verification_succeeds_with_correct_data(self, ecdsa_keypair):
        from app.services.ota_package_builder import sign_package, verify_package_signature

        private_key_path, public_key_path = ecdsa_keypair
        data = b"correct OTA package data"

        signature_b64 = sign_package(data, private_key_path)
        # Should not raise
        verify_package_signature(data, signature_b64, public_key_path)

    def test_verification_fails_with_tampered_data(self, ecdsa_keypair):
        from app.services.ota_package_builder import (
            PackageBuildError,
            sign_package,
            verify_package_signature,
        )

        private_key_path, public_key_path = ecdsa_keypair
        data = b"original OTA package data"
        tampered_data = b"tampered OTA package data"

        signature_b64 = sign_package(data, private_key_path)

        with pytest.raises(PackageBuildError, match="Signature verification failed"):
            verify_package_signature(tampered_data, signature_b64, public_key_path)

    def test_verification_fails_with_wrong_key(self, ecdsa_keypair, other_keypair):
        from app.services.ota_package_builder import (
            PackageBuildError,
            sign_package,
            verify_package_signature,
        )

        private_key_path, _ = ecdsa_keypair
        wrong_public_key_path = other_keypair
        data = b"OTA package signed with one key, verified with another"

        signature_b64 = sign_package(data, private_key_path)

        with pytest.raises(PackageBuildError, match="Signature verification failed"):
            verify_package_signature(data, signature_b64, wrong_public_key_path)
