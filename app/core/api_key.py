"""
API Key utilities for generation and hashing
"""
import secrets
import hashlib


def generate_api_key() -> str:
    """
    Generate a secure API key
    Format: urisocial_<32 random chars>
    """
    random_part = secrets.token_urlsafe(32)
    return f"urisocial_{random_part}"


def hash_api_key(api_key: str) -> str:
    """Hash an API key using SHA256"""
    return hashlib.sha256(api_key.encode()).hexdigest()


def get_key_prefix(api_key: str) -> str:
    """Get the first 15 characters for display"""
    return api_key[:15] + "..." if len(api_key) > 15 else api_key
