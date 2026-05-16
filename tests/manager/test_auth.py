"""Tests for manager authentication module."""

from datetime import timedelta

from nanobot.manager.auth import (
    create_access_token,
    create_admin_token,
    decode_access_token,
    hash_password,
    verify_password,
)


class TestPasswordHashing:
    def test_hash_and_verify(self):
        hashed = hash_password("secret123")
        assert hashed != "secret123"
        assert verify_password("secret123", hashed) is True

    def test_wrong_password(self):
        hashed = hash_password("secret123")
        assert verify_password("wrong", hashed) is False

    def test_different_hashes_for_same_password(self):
        h1 = hash_password("same")
        h2 = hash_password("same")
        assert h1 != h2
        assert verify_password("same", h1)
        assert verify_password("same", h2)


class TestJWT:
    def test_create_and_decode(self):
        secret = "test-secret"
        token = create_access_token({"sub": "user123"}, secret)
        payload = decode_access_token(token, secret)
        assert payload is not None
        assert payload["sub"] == "user123"

    def test_expired_token(self):
        secret = "test-secret"
        token = create_access_token(
            {"sub": "user123"}, secret, expires_delta=timedelta(seconds=-1)
        )
        payload = decode_access_token(token, secret)
        assert payload is None

    def test_invalid_token(self):
        payload = decode_access_token("invalid.token.here", "secret")
        assert payload is None

    def test_wrong_secret(self):
        token = create_access_token({"sub": "user123"}, "secret-a")
        payload = decode_access_token(token, "secret-b")
        assert payload is None


class TestAdminToken:
    def test_correct_password(self):
        token = create_admin_token("admin123", "admin123", "secret")
        assert token is not None
        payload = decode_access_token(token, "secret")
        assert payload is not None
        assert payload["role"] == "admin"

    def test_wrong_password(self):
        token = create_admin_token("wrong", "admin123", "secret")
        assert token is None
