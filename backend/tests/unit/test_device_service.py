from app.services.auth_service import hash_api_key


def test_api_key_hash_consistency():
    """Test that hashing the same key twice produces the same hash."""
    key = "bugsi_test_key_12345"
    h1 = hash_api_key(key)
    h2 = hash_api_key(key)
    assert h1 == h2


def test_api_key_hash_different_for_different_keys():
    h1 = hash_api_key("bugsi_key_1")
    h2 = hash_api_key("bugsi_key_2")
    assert h1 != h2
