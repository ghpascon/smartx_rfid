import re
import jwt
from datetime import datetime, timedelta, timezone
from typing import Dict, Any, Optional
from fastapi import Request

from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError, InvalidHash


class AuthManager:
    def __init__(
        self,
        secret: Optional[str] = None,
        expiration_minutes: int = 15,
        algorithm: str = "HS256",
    ) -> None:
        """
        Initialize AuthManager.

        Args:
            secret (str | None):
                Secret key for signing JWT.
                If None, defaults to datetime-based secret.
            expiration_minutes (int):
                Token expiration time in minutes (default: 15).
            algorithm (str):
                JWT signing algorithm (default: HS256).
        """

        # ⚠️ Dev-only default secret
        self._secret = secret or datetime.now(timezone.utc).isoformat()

        self._expiration_minutes = expiration_minutes
        self._algorithm = algorithm

        # Secure Argon2 configuration
        self._password_hasher = PasswordHasher(
            time_cost=3,
            memory_cost=65536,
            parallelism=4,
        )

    # =====================================================
    # PASSWORD MANAGEMENT
    # =====================================================

    def _validate_password_strength(self, password: str) -> None:
        """
        Enforce password strength policy.

        Rules:
            - At least 8 characters
            - At least one uppercase letter
            - At least one lowercase letter
            - At least one digit
            - At least one special character (!@#$%^&* etc.)

        Raises:
            ValueError with a descriptive message if any rule is violated.
        """
        errors = []

        if len(password) < 8:
            errors.append("at least 8 characters")
        if not re.search(r"[A-Z]", password):
            errors.append("at least one uppercase letter")
        if not re.search(r"[a-z]", password):
            errors.append("at least one lowercase letter")
        if not re.search(r"\d", password):
            errors.append("at least one digit")
        if not re.search(r"[!@#$%^&*()\-_=+\[\]{};:'\",.<>/?\\|`~]", password):
            errors.append("at least one special character")

        if errors:
            raise ValueError(f"Password must contain: {', '.join(errors)}.")

    def hash_password(self, plain_password: str) -> str:
        """
        Hash a password using Argon2.

        Args:
            plain_password (str)

        Returns:
            str: Hashed password
        """
        if not plain_password:
            raise ValueError("Password cannot be empty.")

        self._validate_password_strength(plain_password)

        return self._password_hasher.hash(plain_password)

    def verify_password(self, plain_password: str, hashed_password: str) -> bool:
        """
        Verify password against stored hash.

        Returns:
            bool
        """
        try:
            return self._password_hasher.verify(hashed_password, plain_password)
        except (VerifyMismatchError, InvalidHash):
            return False

    # =====================================================
    # JWT TOKEN
    # =====================================================

    def create_token(self, data: Dict[str, Any]) -> str:
        """
        Create a signed JWT token.

        Args:
            data (dict):
                Dictionary containing user claims
                (e.g. {"user_id": 1, "role": "admin"})

        Returns:
            str: Encoded JWT
        """

        if not isinstance(data, dict):
            raise TypeError("Token payload must be a dictionary.")

        now = datetime.now(timezone.utc)
        expiration = now + timedelta(minutes=self._expiration_minutes)

        payload = {
            **data,
            "iat": now,
            "exp": expiration,
        }

        return jwt.encode(payload, self._secret, algorithm=self._algorithm)

    def decode_token(self, token: str) -> tuple[bool, Optional[Dict[str, Any]]]:
        """
        Decode and validate a JWT token.

        Args:
            token (str)

        Returns:
            tuple[bool, dict | None]:
                (True, payload) if valid,
                (False, None) if invalid or expired.
        """
        try:
            payload = jwt.decode(
                token,
                self._secret,
                algorithms=[self._algorithm],
                options={"require": ["exp", "iat"]},
            )
            return True, payload
        except jwt.PyJWTError:
            return False, None

    def get_user(self, request: Request) -> Optional[Dict[str, Any]]:
        """Return the decoded user claims from the request's Authorization token."""
        token = request.cookies.get("Authorization") or request.headers.get("Authorization")
        if not token:
            return None

        if token.startswith("Bearer "):
            token = token[7:]

        valid, user = self.decode_token(token)
        return user if valid else None

    def validate_role(self, request: Request, required_role: str | list[str]) -> bool:
        """Check whether the authenticated user has any required role."""
        user = self.get_user(request)
        if not user:
            return False

        roles = user.get("roles", [])
        if isinstance(required_role, str):
            return required_role in roles
        return any(role in roles for role in required_role)
