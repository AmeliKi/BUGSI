from app.services.auth_service import (
    create_access_token,
    create_refresh_token,
    decode_token,
    generate_api_key,
    hash_api_key,
    hash_password,
    verify_password,
)


class TestPasswordHashing:
    def test_hash_and_verify(self):
        password = "test_password_123"
        hashed = hash_password(password)
        assert hashed != password
        assert verify_password(password, hashed)

    def test_wrong_password_fails(self):
        hashed = hash_password("correct_password")
        assert not verify_password("wrong_password", hashed)

    def test_different_hashes_for_same_password(self):
        h1 = hash_password("same_password")
        h2 = hash_password("same_password")
        assert h1 != h2  # bcrypt uses random salt


class TestApiKey:
    def test_generate_api_key_format(self):
        plaintext, key_hash, prefix = generate_api_key()
        assert plaintext.startswith("bugsi_")
        assert len(prefix) == 8
        assert prefix == plaintext[:8]
        assert len(key_hash) == 64  # SHA-256 hex digest

    def test_hash_api_key_matches(self):
        plaintext, key_hash, _ = generate_api_key()
        assert hash_api_key(plaintext) == key_hash

    def test_different_keys_each_call(self):
        key1, _, _ = generate_api_key()
        key2, _, _ = generate_api_key()
        assert key1 != key2


class TestJWT:
    def test_create_and_decode_access_token(self):
        token = create_access_token("user-123", "admin")
        payload = decode_token(token)
        assert payload["sub"] == "user-123"
        assert payload["role"] == "admin"
        assert payload["type"] == "access"

    def test_create_and_decode_refresh_token(self):
        token = create_refresh_token("user-456")
        payload = decode_token(token)
        assert payload["sub"] == "user-456"
        assert payload["type"] == "refresh"

    def test_access_token_has_role(self):
        token = create_access_token("user-1", "user")
        payload = decode_token(token)
        assert payload["role"] == "user"
