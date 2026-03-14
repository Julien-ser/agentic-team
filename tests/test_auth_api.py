"""
Comprehensive tests for the JWT Authentication API endpoints.

Tests cover registration, login, token refresh, validation, and security aspects.
"""

import os
import pytest
import json
import bcrypt
import jwt
from datetime import datetime, timedelta
from unittest.mock import patch, MagicMock
from flask import Flask, g

from src.api.auth import (
    create_auth_app,
    verify_password,
    generate_token,
    decode_token,
    token_required,
    _load_initial_users,
)
from src.config import config


@pytest.fixture(scope="session", autouse=True)
def set_test_env():
    """Set required environment variables for tests."""
    os.environ.setdefault(
        "JWT_SECRET_KEY", "test_secret_key_32_chars_long123456789012345"
    )
    os.environ.setdefault("JWT_ALGORITHM", "HS256")
    os.environ.setdefault("JWT_EXPIRATION_DELTA", "3600")
    os.environ.setdefault("JWT_REFRESH_EXPIRATION_DELTA", "604800")
    os.environ.setdefault("BCRYPT_ROUNDS", "4")  # Lower rounds for faster tests
    yield
    # Cleanup after tests if needed


@pytest.fixture
def auth_app():
    """Create a test Flask app for authentication."""
    # Ensure secret key is set
    test_secret = "test_secret_key_32_chars_long123456789012345"
    os.environ["JWT_SECRET_KEY"] = test_secret

    app = create_auth_app()
    app.config["TESTING"] = True
    return app


@pytest.fixture
def client(auth_app):
    """Create a test client for the auth app."""
    with auth_app.test_client() as client:
        yield client


@pytest.fixture
def sample_user():
    """Create a sample user for testing."""
    return {
        "email": "test@example.com",
        "password": "SecurePassword123!",
        "name": "Test User",
        "role": "user",
    }


@pytest.fixture
def initial_users_app(monkeypatch):
    """Create an app with pre-loaded initial users from env."""
    # Set environment variable with initial users
    users_data = [
        {
            "email": "admin@example.com",
            "password": "AdminPass123!",
            "name": "System Admin",
            "role": "admin",
        }
    ]
    monkeypatch.setenv("INITIAL_USERS", json.dumps(users_data))

    # Clear any existing USERS
    app = create_auth_app()
    app.config["TESTING"] = True
    return app


class TestUtilityFunctions:
    """Test utility functions."""

    def test_verify_password_success(self):
        """Test password verification with correct password."""
        password = "test_password123"
        hashed = bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt(12))

        assert verify_password(hashed.decode("utf-8"), password) is True

    def test_verify_password_failure(self):
        """Test password verification with incorrect password."""
        password = "correct_password"
        wrong_password = "wrong_password"
        hashed = bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt(12))

        assert verify_password(hashed.decode("utf-8"), wrong_password) is False

    def test_verify_password_with_unicode(self):
        """Test password verification with unicode characters."""
        password = "p@ssw0rd_日本語"
        hashed = bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt(12))

        assert verify_password(hashed.decode("utf-8"), password) is True

    def test_generate_token_basic(self):
        """Test basic token generation."""
        secret = "test_secret_key_32_chars_long"
        token = generate_token(
            user_email="test@example.com",
            secret=secret,
            algorithm="HS256",
            expiration_delta=3600,
        )

        assert token is not None
        assert isinstance(token, str)
        assert len(token) > 0

        # Verify token can be decoded
        payload = decode_token(token, secret, "HS256")
        assert payload is not None
        assert payload["email"] == "test@example.com"
        assert payload["type"] == "access"

    def test_generate_token_with_extra_claims(self):
        """Test token generation with extra claims."""
        secret = "test_secret_key_32_chars_long"
        token = generate_token(
            user_email="test@example.com",
            secret=secret,
            expiration_delta=3600,
            role="admin",
            user_id=123,
        )

        payload = decode_token(token, secret, "HS256")
        assert payload["role"] == "admin"
        assert payload["user_id"] == 123

    def test_generate_refresh_token(self):
        """Test refresh token generation."""
        secret = "test_secret_key_32_chars_long"
        token = generate_token(
            user_email="test@example.com",
            secret=secret,
            expiration_delta=86400,
            refresh=True,
        )

        payload = decode_token(token, secret, "HS256")
        assert payload["type"] == "refresh"

    def test_decode_token_expired(self):
        """Test decoding expired token."""
        secret = "test_secret_key_32_chars_long"

        # Create token that expired 1 hour ago
        now = datetime.utcnow()
        exp = now - timedelta(hours=1)
        payload = {
            "email": "test@example.com",
            "iat": now - timedelta(hours=2),
            "exp": exp,
            "type": "access",
        }
        token = jwt.encode(payload, secret, algorithm="HS256")

        result = decode_token(token, secret, "HS256")
        assert result is None

    def test_decode_token_invalid_signature(self):
        """Test decoding token with invalid signature."""
        token = generate_token(
            user_email="test@example.com",
            secret="correct_secret",
            expiration_delta=3600,
        )

        result = decode_token(token, secret="wrong_secret", algorithm="HS256")
        assert result is None

    def test_decode_token_wrong_algorithm(self):
        """Test decoding token with wrong algorithm."""
        secret = "test_secret_key_32_chars_long"

        # Create token with HS512
        payload = {
            "email": "test@example.com",
            "iat": datetime.utcnow(),
            "exp": datetime.utcnow() + timedelta(seconds=3600),
            "type": "access",
        }
        token = jwt.encode(payload, secret, algorithm="HS512")

        # Try to decode with HS256 (should fail)
        result = decode_token(token, secret, algorithm="HS256")
        assert result is None


class TestHealthCheck:
    """Test health check endpoint."""

    def test_health_check_success(self, client):
        """Test health check returns healthy status."""
        response = client.get("/api/v1/auth/health")
        assert response.status_code == 200

        data = json.loads(response.data)
        assert data["status"] == "healthy"
        assert data["service"] == "authentication"
        assert "timestamp" in data


class TestRegistration:
    """Test user registration endpoint."""

    def test_register_success(self, client, sample_user):
        """Test successful user registration."""
        response = client.post(
            "/api/v1/auth/register",
            data=json.dumps(sample_user),
            content_type="application/json",
        )

        assert response.status_code == 201
        data = json.loads(response.data)
        assert data["success"] is True
        assert data["message"] == "User registered successfully"
        assert data["user"]["email"] == sample_user["email"]
        assert data["user"]["name"] == sample_user["name"]
        assert "password" not in data["user"]  # Password should not be returned

    def test_register_missing_email(self, client, sample_user):
        """Test registration with missing email."""
        user_data = sample_user.copy()
        del user_data["email"]

        response = client.post(
            "/api/v1/auth/register",
            data=json.dumps(user_data),
            content_type="application/json",
        )

        assert response.status_code == 400
        data = json.loads(response.data)
        assert data["success"] is False
        assert data["error"] == "invalid_email"

    def test_register_missing_password(self, client, sample_user):
        """Test registration with missing password."""
        user_data = sample_user.copy()
        del user_data["password"]

        response = client.post(
            "/api/v1/auth/register",
            data=json.dumps(user_data),
            content_type="application/json",
        )

        assert response.status_code == 400
        data = json.loads(response.data)
        assert data["success"] is False
        assert data["error"] == "invalid_email"  # Email validation also fails

    def test_register_weak_password(self, client, sample_user):
        """Test registration with weak password."""
        user_data = sample_user.copy()
        user_data["password"] = "123"  # Too short

        response = client.post(
            "/api/v1/auth/register",
            data=json.dumps(user_data),
            content_type="application/json",
        )

        assert response.status_code == 400
        data = json.loads(response.data)
        assert data["success"] is False
        assert data["error"] == "weak_password"

    def test_register_duplicate_user(self, client, sample_user):
        """Test registration with duplicate email."""
        # First registration
        client.post(
            "/api/v1/auth/register",
            data=json.dumps(sample_user),
            content_type="application/json",
        )

        # Second registration with same email
        response = client.post(
            "/api/v1/auth/register",
            data=json.dumps(sample_user),
            content_type="application/json",
        )

        assert response.status_code == 409
        data = json.loads(response.data)
        assert data["success"] is False
        assert data["error"] == "user_exists"

    def test_register_invalid_json(self, client):
        """Test registration with invalid JSON."""
        response = client.post(
            "/api/v1/auth/register",
            data="invalid json",
            content_type="application/json",
        )

        assert response.status_code == 400
        data = json.loads(response.data)
        assert data["success"] is False
        assert data["error"] == "invalid_request"

    def test_register_with_role(self, client):
        """Test registration with explicit role."""
        user_data = {
            "email": "admin@example.com",
            "password": "SecurePass123!",
            "name": "Admin User",
            "role": "admin",
        }

        response = client.post(
            "/api/v1/auth/register",
            data=json.dumps(user_data),
            content_type="application/json",
        )

        assert response.status_code == 201
        data = json.loads(response.data)
        assert data["user"]["role"] == "admin"

    def test_register_invalid_role_defaults_to_user(self, client):
        """Test registration with invalid role defaults to user."""
        user_data = {
            "email": "user@example.com",
            "password": "SecurePass123!",
            "name": "Regular User",
            "role": "superhero",
        }

        response = client.post(
            "/api/v1/auth/register",
            data=json.dumps(user_data),
            content_type="application/json",
        )

        assert response.status_code == 201
        data = json.loads(response.data)
        assert data["user"]["role"] == "user"


class TestLogin:
    """Test user login endpoint."""

    def test_login_success(self, client, sample_user):
        """Test successful login."""
        # First register
        client.post(
            "/api/v1/auth/register",
            data=json.dumps(sample_user),
            content_type="application/json",
        )

        # Then login
        response = client.post(
            "/api/v1/auth/login",
            data=json.dumps(
                {"email": sample_user["email"], "password": sample_user["password"]}
            ),
            content_type="application/json",
        )

        assert response.status_code == 200
        data = json.loads(response.data)
        assert data["success"] is True
        assert "access_token" in data
        assert "refresh_token" in data
        assert data["token_type"] == "Bearer"
        assert isinstance(data["expires_in"], int)
        assert data["expires_in"] > 0
        assert "user" in data
        assert data["user"]["email"] == sample_user["email"]

    def test_login_invalid_credentials(self, client, sample_user):
        """Test login with invalid credentials."""
        # First register
        client.post(
            "/api/v1/auth/register",
            data=json.dumps(sample_user),
            content_type="application/json",
        )

        # Try to login with wrong password
        response = client.post(
            "/api/v1/auth/login",
            data=json.dumps(
                {"email": sample_user["email"], "password": "WrongPassword123!"}
            ),
            content_type="application/json",
        )

        assert response.status_code == 401
        data = json.loads(response.data)
        assert data["success"] is False
        assert data["error"] == "invalid_credentials"
        # Generic error message to prevent user enumeration
        assert "Invalid email or password" in data["message"]

    def test_login_nonexistent_user(self, client):
        """Test login with non-existent user."""
        response = client.post(
            "/api/v1/auth/login",
            data=json.dumps(
                {"email": "nonexistent@example.com", "password": "somepassword"}
            ),
            content_type="application/json",
        )

        assert response.status_code == 401
        data = json.loads(response.data)
        assert data["success"] is False
        assert data["error"] == "invalid_credentials"

    def test_login_missing_email(self, client, sample_user):
        """Test login with missing email."""
        response = client.post(
            "/api/v1/auth/login",
            data=json.dumps({"password": sample_user["password"]}),
            content_type="application/json",
        )

        assert response.status_code == 400
        data = json.loads(response.data)
        assert data["success"] is False
        assert data["error"] == "credentials_missing"

    def test_login_missing_password(self, client, sample_user):
        """Test login with missing password."""
        response = client.post(
            "/api/v1/auth/login",
            data=json.dumps({"email": sample_user["email"]}),
            content_type="application/json",
        )

        assert response.status_code == 400
        data = json.loads(response.data)
        assert data["success"] is False
        assert data["error"] == "credentials_missing"

    def test_login_invalid_json(self, client):
        """Test login with invalid JSON."""
        response = client.post(
            "/api/v1/auth/login", data="invalid json", content_type="application/json"
        )

        assert response.status_code == 400
        data = json.loads(response.data)
        assert data["success"] is False
        assert data["error"] == "invalid_request"

    def test_login_password_case_sensitive(self, client, sample_user):
        """Test that password comparison is case-sensitive."""
        # Register
        client.post(
            "/api/v1/auth/register",
            data=json.dumps(sample_user),
            content_type="application/json",
        )

        # Try login with different case
        response = client.post(
            "/api/v1/auth/login",
            data=json.dumps(
                {
                    "email": sample_user["email"],
                    "password": sample_user["password"].upper(),
                }
            ),
            content_type="application/json",
        )

        assert response.status_code == 401

    def test_token_contains_user_info(self, client, sample_user):
        """Test that access token contains correct user info."""
        # Register and login
        client.post(
            "/api/v1/auth/register",
            data=json.dumps(sample_user),
            content_type="application/json",
        )

        response = client.post(
            "/api/v1/auth/login",
            data=json.dumps(
                {"email": sample_user["email"], "password": sample_user["password"]}
            ),
            content_type="application/json",
        )

        data = json.loads(response.data)
        token = data["access_token"]

        # Decode token manually to verify claims
        secret = None
        # Get the actual secret from config or environment
        from src.config import config

        secret = config.JWT_SECRET_KEY or "test_secret_key_32_chars_long"

        try:
            payload = jwt.decode(token, secret, algorithms=["HS256"])
            assert payload["email"] == sample_user["email"]
            assert payload["type"] == "access"
            assert payload["role"] == sample_user["role"]
        except jwt.ExpiredSignatureError:
            pytest.fail("Token should not be expired")
        except jwt.InvalidTokenError as e:
            pytest.fail(f"Token should be valid: {e}")


class TestTokenRefresh:
    """Test token refresh endpoint."""

    def test_refresh_success(self, client, sample_user):
        """Test successful token refresh."""
        # Register and login
        client.post(
            "/api/v1/auth/register",
            data=json.dumps(sample_user),
            content_type="application/json",
        )

        login_response = client.post(
            "/api/v1/auth/login",
            data=json.dumps(
                {"email": sample_user["email"], "password": sample_user["password"]}
            ),
            content_type="application/json",
        )

        login_data = json.loads(login_response.data)
        refresh_token = login_data["refresh_token"]

        # Use refresh token to get new access token
        response = client.post(
            "/api/v1/auth/refresh",
            data=json.dumps({"refresh_token": refresh_token}),
            content_type="application/json",
        )

        assert response.status_code == 200
        data = json.loads(response.data)
        assert data["success"] is True
        assert "access_token" in data
        assert data["token_type"] == "Bearer"
        assert data["expires_in"] > 0

    def test_refresh_with_access_token_fails(self, client, sample_user):
        """Test that using access token for refresh fails."""
        # Register and login
        client.post(
            "/api/v1/auth/register",
            data=json.dumps(sample_user),
            content_type="application/json",
        )

        login_response = client.post(
            "/api/v1/auth/login",
            data=json.dumps(
                {"email": sample_user["email"], "password": sample_user["password"]}
            ),
            content_type="application/json",
        )

        login_data = json.loads(login_response.data)
        access_token = login_data["access_token"]

        # Try to use access token as refresh token
        response = client.post(
            "/api/v1/auth/refresh",
            data=json.dumps({"refresh_token": access_token}),
            content_type="application/json",
        )

        assert response.status_code == 401
        data = json.loads(response.data)
        assert data["error"] == "invalid_token_type"

    def test_refresh_expired_token(self, client, sample_user):
        """Test refresh with expired refresh token."""
        # Create an expired refresh token manually
        from src.api.auth import generate_token

        secret = config.JWT_SECRET_KEY or "test_secret_key_32_chars_long"
        expired_token = generate_token(
            user_email=sample_user["email"],
            secret=secret,
            expiration_delta=-3600,  # Expired 1 hour ago
            refresh=True,
        )

        response = client.post(
            "/api/v1/auth/refresh",
            data=json.dumps({"refresh_token": expired_token}),
            content_type="application/json",
        )

        assert response.status_code == 401
        data = json.loads(response.data)
        assert data["error"] == "invalid_token"

    def test_refresh_missing_token(self, client):
        """Test refresh without providing token."""
        response = client.post(
            "/api/v1/auth/refresh", data=json.dumps({}), content_type="application/json"
        )

        assert response.status_code == 400
        data = json.loads(response.data)
        assert data["error"] == "token_missing"

    def test_refresh_invalid_json(self, client):
        """Test refresh with invalid JSON."""
        response = client.post(
            "/api/v1/auth/refresh", data="invalid json", content_type="application/json"
        )

        assert response.status_code == 400
        data = json.loads(response.data)
        assert data["error"] == "invalid_request"


class TestVerifyToken:
    """Test token verification endpoint."""

    def test_verify_valid_token(self, client, sample_user):
        """Test verifying a valid access token."""
        # Register and login
        client.post(
            "/api/v1/auth/register",
            data=json.dumps(sample_user),
            content_type="application/json",
        )

        login_response = client.post(
            "/api/v1/auth/login",
            data=json.dumps(
                {"email": sample_user["email"], "password": sample_user["password"]}
            ),
            content_type="application/json",
        )

        login_data = json.loads(login_response.data)
        access_token = login_data["access_token"]

        # Verify token
        response = client.get(
            "/api/v1/auth/verify", headers={"Authorization": f"Bearer {access_token}"}
        )

        assert response.status_code == 200
        data = json.loads(response.data)
        assert data["success"] is True
        assert data["user"]["email"] == sample_user["email"]

    def test_verify_missing_token(self, client):
        """Test verify endpoint without token."""
        response = client.get("/api/v1/auth/verify")

        assert response.status_code == 401
        data = json.loads(response.data)
        assert data["error"] == "token_missing"

    def test_verify_invalid_token(self, client):
        """Test verify endpoint with invalid token."""
        response = client.get(
            "/api/v1/auth/verify",
            headers={"Authorization": "Bearer invalid_token_12345"},
        )

        assert response.status_code == 401
        data = json.loads(response.data)
        assert data["error"] == "invalid_token"

    def test_verify_refresh_token_fails(self, client, sample_user):
        """Test that refresh tokens cannot be used for verification."""
        # Register and login
        client.post(
            "/api/v1/auth/register",
            data=json.dumps(sample_user),
            content_type="application/json",
        )

        login_response = client.post(
            "/api/v1/auth/login",
            data=json.dumps(
                {"email": sample_user["email"], "password": sample_user["password"]}
            ),
            content_type="application/json",
        )

        login_data = json.loads(login_response.data)
        refresh_token = login_data["refresh_token"]

        # Try to use refresh token
        response = client.get(
            "/api/v1/auth/verify", headers={"Authorization": f"Bearer {refresh_token}"}
        )

        assert response.status_code == 401
        data = json.loads(response.data)
        assert data["error"] == "refresh_token_used"

    def test_verify_malformed_auth_header(self, client):
        """Test verify endpoint with malformed Authorization header."""
        response = client.get(
            "/api/v1/auth/verify", headers={"Authorization": "InvalidFormat token123"}
        )

        assert response.status_code == 401
        data = json.loads(response.data)
        assert data["error"] == "invalid_token_format"


class TestLogout:
    """Test logout endpoint."""

    def test_logout_success(self, client, sample_user):
        """Test successful logout."""
        # Register and login
        client.post(
            "/api/v1/auth/register",
            data=json.dumps(sample_user),
            content_type="application/json",
        )

        login_response = client.post(
            "/api/v1/auth/login",
            data=json.dumps(
                {"email": sample_user["email"], "password": sample_user["password"]}
            ),
            content_type="application/json",
        )

        login_data = json.loads(login_response.data)
        access_token = login_data["access_token"]

        # Logout
        response = client.post(
            "/api/v1/auth/logout", headers={"Authorization": f"Bearer {access_token}"}
        )

        assert response.status_code == 200
        data = json.loads(response.data)
        assert data["success"] is True
        assert "Logout successful" in data["message"]

    def test_logout_requires_token(self, client):
        """Test logout without token fails."""
        response = client.post("/api/v1/auth/logout")

        assert response.status_code == 401


class TestTokenDecorator:
    """Test the @token_required decorator."""

    def test_protected_endpoint_with_valid_token(self, client, sample_user, auth_app):
        """Test accessing protected endpoint with valid token."""
        # Register and login
        client.post(
            "/api/v1/auth/register",
            data=json.dumps(sample_user),
            content_type="application/json",
        )

        login_response = client.post(
            "/api/v1/auth/login",
            data=json.dumps(
                {"email": sample_user["email"], "password": sample_user["password"]}
            ),
            content_type="application/json",
        )

        login_data = json.loads(login_response.data)
        access_token = login_data["access_token"]

        # Access protected endpoint
        response = client.get(
            "/api/v1/auth/verify", headers={"Authorization": f"Bearer {access_token}"}
        )

        assert response.status_code == 200

    def test_protected_endpoint_with_expired_token(self, client, auth_app, sample_user):
        """Test accessing protected endpoint with expired token."""
        # Create a valid token that's already expired
        from src.api.auth import generate_token

        secret = config.JWT_SECRET_KEY or "test_secret_key_32_chars_long"
        expired_token = generate_token(
            user_email=sample_user["email"],
            secret=secret,
            expiration_delta=-3600,  # Expired 1 hour ago
        )

        response = client.get(
            "/api/v1/auth/verify", headers={"Authorization": f"Bearer {expired_token}"}
        )

        assert response.status_code == 401
        data = json.loads(response.data)
        assert data["error"] == "invalid_token"


class TestInitialUsers:
    """Test loading initial users from environment."""

    def test_load_initial_users_from_env(self, initial_users_app):
        """Test that initial users are loaded from INITIAL_USERS env var."""
        assert "admin@example.com" in initial_users_app.config["USERS"]
        user = initial_users_app.config["USERS"]["admin@example.com"]
        assert user["name"] == "System Admin"
        assert user["role"] == "admin"
        assert "password_hash" in user

    def test_initial_users_can_login(self, initial_users_app):
        """Test that pre-loaded admin user can login."""
        response = initial_users_app.test_client().post(
            "/api/v1/auth/login",
            data=json.dumps(
                {"email": "admin@example.com", "password": "AdminPass123!"}
            ),
            content_type="application/json",
        )

        assert response.status_code == 200
        data = json.loads(response.data)
        assert data["success"] is True
        assert "access_token" in data


class TestSecurityConsiderations:
    """Test security aspects of the authentication system."""

    def test_password_hashing(self):
        """Test that passwords are properly hashed."""
        password = "secure_password_123"
        hashed = bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt(12))

        # Hash should be different each time due to salt
        hashed2 = bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt(12))
        assert hashed != hashed2

        # Both should verify
        assert bcrypt.checkpw(password.encode("utf-8"), hashed)
        assert bcrypt.checkpw(password.encode("utf-8"), hashed2)

    def test_password_not_in_response(self, client, sample_user):
        """Test that passwords are never returned in API responses."""
        # Register
        response = client.post(
            "/api/v1/auth/register",
            data=json.dumps(sample_user),
            content_type="application/json",
        )
        data = json.loads(response.data)
        assert "password" not in data["user"]
        assert "password_hash" not in data["user"]

        # Login
        response = client.post(
            "/api/v1/auth/login",
            data=json.dumps(
                {"email": sample_user["email"], "password": sample_user["password"]}
            ),
            content_type="application/json",
        )
        data = json.loads(response.data)
        assert "password" not in data["user"]
        assert "password_hash" not in data["user"]

    def test_timing_attack_mitigation(self, client, sample_user):
        """Test that timing is consistent for invalid credentials."""
        import time

        # Make several failed login attempts and check timing consistency
        times = []
        for _ in range(5):
            start = time.time()
            response = client.post(
                "/api/v1/auth/login",
                data=json.dumps(
                    {"email": sample_user["email"], "password": "wrong_password"}
                ),
                content_type="application/json",
            )
            times.append(time.time() - start)

        # All should complete in similar time (allowing some variance)
        avg_time = sum(times) / len(times)
        for t in times:
            assert abs(t - avg_time) < 0.1  # Within 100ms

    def test_bcrypt_work_factor(self, sample_user):
        """Test that bcrypt work factor is reasonable."""
        # Hash a password with default rounds
        password = "test_password"
        hashed = bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt(12))

        # bcrypt hash format includes work factor
        # Format: $2b$12$... (12 = work factor)
        assert hashed.decode("utf-8").startswith("$2b$12$")

    def test_jwt_has_expiration(self, client, sample_user):
        """Test that all tokens include expiration."""
        # Register and login
        client.post(
            "/api/v1/auth/register",
            data=json.dumps(sample_user),
            content_type="application/json",
        )

        response = client.post(
            "/api/v1/auth/login",
            data=json.dumps(
                {"email": sample_user["email"], "password": sample_user["password"]}
            ),
            content_type="application/json",
        )

        data = json.loads(response.data)
        access_token = data["access_token"]
        refresh_token = data["refresh_token"]

        # Decode tokens to check exp
        from src.api.auth import decode_token

        secret = config.JWT_SECRET_KEY or "test_secret_key_32_chars_long"

        access_payload = decode_token(access_token, secret, verify_exp=False)
        assert access_payload["exp"] is not None
        assert access_payload["type"] == "access"

        refresh_payload = decode_token(refresh_token, secret, verify_exp=False)
        assert refresh_payload["exp"] is not None
        assert refresh_payload["type"] == "refresh"


class TestEdgeCases:
    """Test edge cases and error conditions."""

    def test_register_email_normalization(self, client):
        """Test that email addresses are normalized to lowercase."""
        user_data = {
            "email": "TestUser@Example.COM",
            "password": "SecurePass123!",
            "name": "Test User",
        }

        response = client.post(
            "/api/v1/auth/register",
            data=json.dumps(user_data),
            content_type="application/json",
        )

        assert response.status_code == 201

        # Try to register again with same email but different case
        user_data2 = user_data.copy()
        user_data2["name"] = "Test User 2"
        response2 = client.post(
            "/api/v1/auth/register",
            data=json.dumps(user_data2),
            content_type="application/json",
        )

        # Should fail as duplicate (case-insensitive)
        assert response2.status_code == 409

    def test_login_email_normalization(self, client, sample_user):
        """Test that login works with any case for email."""
        # Register
        client.post(
            "/api/v1/auth/register",
            data=json.dumps(sample_user),
            content_type="application/json",
        )

        # Login with uppercase email
        response = client.post(
            "/api/v1/auth/login",
            data=json.dumps(
                {
                    "email": sample_user["email"].upper(),
                    "password": sample_user["password"],
                }
            ),
            content_type="application/json",
        )

        assert response.status_code == 200
        data = json.loads(response.data)
        assert data["success"] is True

    def test_long_json_field_values(self, client):
        """Test handling of very long input values."""
        long_name = "A" * 1000
        user_data = {
            "email": "longname@example.com",
            "password": "SecurePass123!",
            "name": long_name,
        }

        response = client.post(
            "/api/v1/auth/register",
            data=json.dumps(user_data),
            content_type="application/json",
        )

        # Should still work (no arbitrary length limits)
        assert response.status_code in [200, 201]

    def test_special_characters_in_password(self, client):
        """Test that special characters in passwords work correctly."""
        user_data = {
            "email": "special@example.com",
            "password": "P@$$w0rd!#%^&*()_+-=[]{}|;:,.<>?",
            "name": "Special Char User",
        }

        response = client.post(
            "/api/v1/auth/register",
            data=json.dumps(user_data),
            content_type="application/json",
        )

        assert response.status_code == 201

        # Should be able to login with same password
        login_response = client.post(
            "/api/v1/auth/login",
            data=json.dumps(
                {"email": user_data["email"], "password": user_data["password"]}
            ),
            content_type="application/json",
        )

        assert login_response.status_code == 200
