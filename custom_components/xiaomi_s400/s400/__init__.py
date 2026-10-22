"""Vendored and adapted S400 protocol code from nokistin/xiaomi-s400-live (Apache-2.0)."""

from .auth import AuthError, BadTokenError
from .body import UserProfile, compute
from .session import S400Session, ScaleEvent, parse_payload

__all__ = [
    "AuthError",
    "BadTokenError",
    "S400Session",
    "ScaleEvent",
    "UserProfile",
    "compute",
    "parse_payload",
]
