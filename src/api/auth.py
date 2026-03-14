"""
Authentication API endpoint with JWT token management.

Provides user authentication, token generation, and protected endpoints
following security best practices (OWASP Top 10 compliant).
"""

import os
import json
import logging
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, List
from functools import wraps

from flask import Flask, request, jsonify, g, current_app
import jwt
import bcrypt
from dotenv import load_dotenv

from src.config import config

load_dotenv()

logger = logging.getLogger(__name__)


def create_auth_app() -> Flask:
    """
    Create and configure the Flask authentication application.

    Returns:
        Configured Flask app instance
    """
    app = Flask(__name__)

    # Configuration from environment variables
    app.config["SECRET_KEY"] = config.JWT_SECRET_KEY or os.getenv("JWT_SECRET_KEY")
    app.config["JWT_ALGORITHM"] = config.JWT_ALGORITHM or "HS256"
    app.config["JWT_EXPIRATION_DELTA"] = int(
        config.JWT_EXPIRATION_DELTA or os.getenv("JWT_EXPIRATION_DELTA", 3600)
    )
    app.config["JWT_REFRESH_EXPIRATION_DELTA"] = int(
        config.JWT_REFRESH_EXPIRATION_DELTA
        or os.getenv("JWT_REFRESH_EXPIRATION_DELTA", 604800)
    )
    app.config["BCRYPT_ROUNDS"] = int(
        config.BCRYPT_ROUNDS or os.getenv("BCRYPT_ROUNDS", 12)
    )

    if not app.config["SECRET_KEY"]:
        raise ValueError(
            "JWT_SECRET_KEY must be set in environment variables. "
            "Generate with: openssl rand -hex 32"
        )

    # Initialize user storage (in production, use a database)
    app.config["USERS"] = {}
    _load_initial_users(app)

    return app


def _load_initial_users(app: Flask) -> None:
    """Load initial users from environment or seed data (development only)."""
    users_json = os.getenv("INITIAL_USERS")
    if users_json:
        try:
            users_data = json.loads(users_json)
            for user in users_data:
                email = user.get("email")
                password = user.get("password")
                if email and password:
                    hashed = bcrypt.hashpw(
                        password.encode("utf-8"),
                        bcrypt.gensalt(app.config["BCRYPT_ROUNDS"]),
                    )
                    app.config["USERS"][email] = {
                        "email": email,
                        "password_hash": hashed.decode("utf-8"),
                        "name": user.get("name", ""),
                        "role": user.get("role", "user"),
                        "created_at": datetime.utcnow().isoformat(),
                    }
            logger.info(f"Loaded {len(app.config['USERS'])} initial users")
        except Exception as e:
            logger.error(f"Failed to load initial users: {e}")


def verify_password(stored_hash: str, provided_password: str) -> bool:
    """
    Verify a password against its stored hash.

    Args:
        stored_hash: Hashed password string
        provided_password: Plain text password to verify

    Returns:
        True if password matches, False otherwise
    """
    try:
        return bcrypt.checkpw(
            provided_password.encode("utf-8"), stored_hash.encode("utf-8")
        )
    except Exception as e:
        logger.error(f"Password verification failed: {e}")
        return False


def generate_token(
    user_email: str,
    secret: str,
    algorithm: str = "HS256",
    expiration_delta: int = 3600,
    refresh: bool = False,
    **extra_claims,
) -> str:
    """
    Generate a JWT token for authentication.

    Args:
        user_email: Email address of the user
        secret: JWT secret key
        algorithm: JWT signing algorithm
        expiration_delta: Token expiration time in seconds
        refresh: Whether this is a refresh token
        **extra_claims: Additional claims to include in token

    Returns:
        Encoded JWT token string
    """
    now = datetime.utcnow()
    payload = {
        "email": user_email,
        "iat": now,
        "exp": now + timedelta(seconds=expiration_delta),
        "type": "refresh" if refresh else "access",
    }
    payload.update(extra_claims)

    return jwt.encode(payload, secret, algorithm=algorithm)


def decode_token(
    token: str, secret: str, algorithm: str = "HS256", verify_exp: bool = True
) -> Optional[Dict[str, Any]]:
    """
    Decode and validate a JWT token.

    Args:
        token: JWT token string
        secret: JWT secret key
        algorithm: JWT signing algorithm
        verify_exp: Whether to verify expiration

    Returns:
        Dictionary of token claims or None if invalid
    """
    try:
        options: Dict[str, Any] = {"verify_exp": verify_exp}
        payload = jwt.decode(
            token,
            secret,
            algorithms=[algorithm],
            options=options,  # type: ignore
        )
        return payload
    except jwt.ExpiredSignatureError:
        logger.warning("Token has expired")
        return None
    except jwt.InvalidTokenError as e:
        logger.warning(f"Invalid token: {e}")
        return None


def token_required(f):
    """
    Decorator to protect endpoints requiring authentication.

    Usage:
        @app.route('/api/protected')
        @token_required
        def protected_endpoint():
            user_email = g.current_user  # Available in endpoint
            return jsonify({'user': user_email})
    """

    @wraps(f)
    def decorated(*args, **kwargs):
        token = None

        # Get token from Authorization header
        auth_header = request.headers.get("Authorization")
        if auth_header:
            try:
                # Expected format: "Bearer <token>"
                parts = auth_header.split()
                if len(parts) == 2 and parts[0].lower() == "bearer":
                    token = parts[1]
            except Exception as e:
                logger.error(f"Error parsing Authorization header: {e}")
                return jsonify(
                    {
                        "success": False,
                        "error": "invalid_token_format",
                        "message": "Invalid Authorization header format",
                    }
                ), 401

        if not token:
            return jsonify(
                {
                    "success": False,
                    "error": "token_missing",
                    "message": "Authentication token is required",
                }
            ), 401

        # Decode and validate token
        secret = current_app.config["SECRET_KEY"]
        algorithm = current_app.config["JWT_ALGORITHM"]

        payload = decode_token(token, secret, algorithm)
        if not payload:
            return jsonify(
                {
                    "success": False,
                    "error": "invalid_token",
                    "message": "Invalid or expired token",
                }
            ), 401

        # Check token type is access token (not refresh)
        if payload.get("type") == "refresh":
            return jsonify(
                {
                    "success": False,
                    "error": "refresh_token_used",
                    "message": "Refresh token cannot be used for authentication",
                }
            ), 401

        # Store user info in Flask's g object
        g.current_user = payload.get("email")
        g.token_payload = payload

        return f(*args, **kwargs)

    return decorated


def create_auth_endpoints(app: Flask) -> None:
    """
    Register authentication endpoint routes.

    Args:
        app: Flask application instance
    """

    @app.route("/api/v1/auth/health", methods=["GET"])
    def health_check():
        """Health check endpoint for auth service."""
        return jsonify(
            {
                "status": "healthy",
                "service": "authentication",
                "timestamp": datetime.utcnow().isoformat(),
            }
        ), 200

    @app.route("/api/v1/auth/register", methods=["POST"])
    def register():
        """
        Register a new user account.

        Expected JSON payload:
        {
            "email": "user@example.com",
            "password": "secure_password",
            "name": "User Name" (optional),
            "role": "user" (optional, default: "user")
        }

        Returns:
            JSON response with user info (excluding password) or error
        """
        try:
            data = request.get_json()
            if not data:
                return jsonify(
                    {
                        "success": False,
                        "error": "invalid_request",
                        "message": "Request body must be JSON",
                    }
                ), 400

            email = data.get("email", "").strip().lower()
            password = data.get("password", "")
            name = data.get("name", "").strip()
            role = data.get("role", "user")

            # Validation
            if not email or "@" not in email:
                return jsonify(
                    {
                        "success": False,
                        "error": "invalid_email",
                        "message": "Valid email address is required",
                    }
                ), 400

            if not password or len(password) < 8:
                return jsonify(
                    {
                        "success": False,
                        "error": "weak_password",
                        "message": "Password must be at least 8 characters",
                    }
                ), 400

            if role not in ["user", "admin", "developer"]:
                role = "user"

            # Check if user already exists
            if email in app.config["USERS"]:
                return jsonify(
                    {
                        "success": False,
                        "error": "user_exists",
                        "message": "User with this email already exists",
                    }
                ), 409

            # Hash password
            hashed = bcrypt.hashpw(
                password.encode("utf-8"), bcrypt.gensalt(app.config["BCRYPT_ROUNDS"])
            )

            # Store user (in production, use database)
            app.config["USERS"][email] = {
                "email": email,
                "password_hash": hashed.decode("utf-8"),
                "name": name,
                "role": role,
                "created_at": datetime.utcnow().isoformat(),
            }

            logger.info(f"New user registered: {email}")

            return jsonify(
                {
                    "success": True,
                    "message": "User registered successfully",
                    "user": {
                        "email": email,
                        "name": name,
                        "role": role,
                        "created_at": app.config["USERS"][email]["created_at"],
                    },
                }
            ), 201

        except Exception as e:
            logger.error(f"Registration error: {e}", exc_info=True)
            return jsonify(
                {
                    "success": False,
                    "error": "server_error",
                    "message": "An error occurred during registration",
                }
            ), 500

    @app.route("/api/v1/auth/login", methods=["POST"])
    def login():
        """
        Authenticate user and return JWT tokens.

        Expected JSON payload:
        {
            "email": "user@example.com",
            "password": "password123"
        }

        Returns:
            JSON response with access_token, refresh_token, and user info,
            or error if authentication fails
        """
        try:
            data = request.get_json()
            if not data:
                return jsonify(
                    {
                        "success": False,
                        "error": "invalid_request",
                        "message": "Request body must be JSON",
                    }
                ), 400

            email = data.get("email", "").strip().lower()
            password = data.get("password", "")

            # Validation
            if not email or not password:
                return jsonify(
                    {
                        "success": False,
                        "error": "credentials_missing",
                        "message": "Email and password are required",
                    }
                ), 400

            # Check user exists
            user = app.config["USERS"].get(email)
            if not user:
                # Use generic error message to avoid user enumeration
                return jsonify(
                    {
                        "success": False,
                        "error": "invalid_credentials",
                        "message": "Invalid email or password",
                    }
                ), 401

            # Verify password
            if not verify_password(user["password_hash"], password):
                return jsonify(
                    {
                        "success": False,
                        "error": "invalid_credentials",
                        "message": "Invalid email or password",
                    }
                ), 401

            # Generate tokens
            secret = app.config["SECRET_KEY"]
            algorithm = app.config["JWT_ALGORITHM"]
            access_exp = app.config["JWT_EXPIRATION_DELTA"]
            refresh_exp = app.config["JWT_REFRESH_EXPIRATION_DELTA"]

            access_token = generate_token(
                user_email=email,
                secret=secret,
                algorithm=algorithm,
                expiration_delta=access_exp,
                refresh=False,
                role=user.get("role", "user"),
            )

            refresh_token = generate_token(
                user_email=email,
                secret=secret,
                algorithm=algorithm,
                expiration_delta=refresh_exp,
                refresh=True,
            )

            logger.info(f"User logged in: {email}")

            return jsonify(
                {
                    "success": True,
                    "message": "Login successful",
                    "access_token": access_token,
                    "refresh_token": refresh_token,
                    "token_type": "Bearer",
                    "expires_in": access_exp,
                    "user": {
                        "email": email,
                        "name": user.get("name", ""),
                        "role": user.get("role", "user"),
                    },
                }
            ), 200

        except Exception as e:
            logger.error(f"Login error: {e}", exc_info=True)
            return jsonify(
                {
                    "success": False,
                    "error": "server_error",
                    "message": "An error occurred during authentication",
                }
            ), 500

    @app.route("/api/v1/auth/refresh", methods=["POST"])
    def refresh():
        """
        Refresh access token using refresh token.

        Expected JSON payload:
        {
            "refresh_token": "refresh_token_string"
        }

        Returns:
            JSON response with new access_token or error
        """
        try:
            data = request.get_json()
            if not data:
                return jsonify(
                    {
                        "success": False,
                        "error": "invalid_request",
                        "message": "Request body must be JSON",
                    }
                ), 400

            refresh_token = data.get("refresh_token", "").strip()
            if not refresh_token:
                return jsonify(
                    {
                        "success": False,
                        "error": "token_missing",
                        "message": "Refresh token is required",
                    }
                ), 400

            # Decode refresh token
            secret = app.config["SECRET_KEY"]
            algorithm = app.config["JWT_ALGORITHM"]
            payload = decode_token(refresh_token, secret, algorithm)

            if not payload:
                return jsonify(
                    {
                        "success": False,
                        "error": "invalid_token",
                        "message": "Invalid or expired refresh token",
                    }
                ), 401

            # Verify it's a refresh token
            if payload.get("type") != "refresh":
                return jsonify(
                    {
                        "success": False,
                        "error": "invalid_token_type",
                        "message": "Provided token is not a refresh token",
                    }
                ), 401

            email = payload.get("email")
            if not email or email not in app.config["USERS"]:
                return jsonify(
                    {
                        "success": False,
                        "error": "user_not_found",
                        "message": "User not found",
                    }
                ), 401

            # Generate new access token
            user = app.config["USERS"][email]
            access_token = generate_token(
                user_email=email,
                secret=secret,
                algorithm=algorithm,
                expiration_delta=app.config["JWT_EXPIRATION_DELTA"],
                refresh=False,
                role=user.get("role", "user"),
            )

            logger.info(f"Token refreshed for: {email}")

            return jsonify(
                {
                    "success": True,
                    "message": "Token refreshed successfully",
                    "access_token": access_token,
                    "token_type": "Bearer",
                    "expires_in": app.config["JWT_EXPIRATION_DELTA"],
                }
            ), 200

        except Exception as e:
            logger.error(f"Token refresh error: {e}", exc_info=True)
            return jsonify(
                {
                    "success": False,
                    "error": "server_error",
                    "message": "An error occurred during token refresh",
                }
            ), 500

    @app.route("/api/v1/auth/verify", methods=["GET"])
    @token_required
    def verify_token():
        """
        Verify current access token and return user info.

        Requires valid Bearer token in Authorization header.

        Returns:
            JSON response with user info and token validity
        """
        user_email = g.current_user
        user = app.config["USERS"].get(user_email)

        if not user:
            return jsonify(
                {
                    "success": False,
                    "error": "user_not_found",
                    "message": "User associated with token not found",
                }
            ), 404

        return jsonify(
            {
                "success": True,
                "message": "Token is valid",
                "user": {
                    "email": user_email,
                    "name": user.get("name", ""),
                    "role": user.get("role", "user"),
                },
                "token_info": {
                    "issued_at": datetime.utcfromtimestamp(
                        g.token_payload.get("iat")
                    ).isoformat()
                    if g.token_payload.get("iat")
                    else None,
                    "expires_at": datetime.utcfromtimestamp(
                        g.token_payload.get("exp")
                    ).isoformat()
                    if g.token_payload.get("exp")
                    else None,
                },
            }
        ), 200

    @app.route("/api/v1/auth/logout", methods=["POST"])
    @token_required
    def logout():
        """
        Logout endpoint (client-side token revocation).

        Note: This endpoint validates the token and informs client to remove it.
        In production, implement token blacklist for stateless JWT invalidation.
        """
        user_email = g.current_user
        logger.info(f"User logged out: {user_email}")

        return jsonify(
            {
                "success": True,
                "message": "Logout successful. Please remove the token from client storage.",
            }
        ), 200

    logger.info("Authentication endpoints registered")


def init_auth_api(app: Flask) -> Flask:
    """
    Initialize authentication API on an existing Flask app.

    Args:
        app: Existing Flask application

    Returns:
        Same Flask app with auth routes added
    """
    create_auth_endpoints(app)
    return app


if __name__ == "__main__":
    # Standalone auth service
    auth_app = create_auth_app()
    create_auth_endpoints(auth_app)

    port = int(os.getenv("AUTH_SERVICE_PORT", 5001))
    auth_app.run(host="0.0.0.0", port=port, debug=True)
