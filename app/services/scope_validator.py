"""
API Key scope and permission validation
"""
from typing import List
from fastapi import HTTPException, status

from app.models.api_key import APIKey, APIKeyScope


# Scope hierarchy - higher scopes include lower ones
SCOPE_HIERARCHY = {
    APIKeyScope.ADMIN: [
        APIKeyScope.SOCIAL_MEDIA_READ,
        APIKeyScope.SOCIAL_MEDIA_WRITE,
        APIKeyScope.SOCIAL_MEDIA_DELETE,
        APIKeyScope.CONTENT_GENERATE,
        APIKeyScope.CONTENT_ANALYZE,
        APIKeyScope.ANALYTICS_READ,
        APIKeyScope.CAMPAIGNS_READ,
        APIKeyScope.CAMPAIGNS_WRITE,
        APIKeyScope.CAMPAIGNS_DELETE,
        APIKeyScope.ACCOUNT_READ,
        APIKeyScope.ACCOUNT_WRITE,
    ],
    APIKeyScope.SOCIAL_MEDIA_WRITE: [
        APIKeyScope.SOCIAL_MEDIA_READ,
    ],
    APIKeyScope.SOCIAL_MEDIA_DELETE: [
        APIKeyScope.SOCIAL_MEDIA_READ,
        APIKeyScope.SOCIAL_MEDIA_WRITE,
    ],
    APIKeyScope.CAMPAIGNS_WRITE: [
        APIKeyScope.CAMPAIGNS_READ,
    ],
    APIKeyScope.CAMPAIGNS_DELETE: [
        APIKeyScope.CAMPAIGNS_READ,
        APIKeyScope.CAMPAIGNS_WRITE,
    ],
    APIKeyScope.ACCOUNT_WRITE: [
        APIKeyScope.ACCOUNT_READ,
    ],
}


def has_scope(api_key: APIKey, required_scope: APIKeyScope) -> bool:
    """
    Check if API key has the required scope

    Args:
        api_key: The API key to check
        required_scope: The scope required

    Returns:
        True if key has scope, False otherwise
    """
    # Direct scope match
    if required_scope in api_key.scopes:
        return True

    # Check hierarchy - if key has higher scope that includes required scope
    for key_scope in api_key.scopes:
        if key_scope in SCOPE_HIERARCHY:
            if required_scope in SCOPE_HIERARCHY[key_scope]:
                return True

    return False


def has_any_scope(api_key: APIKey, required_scopes: List[APIKeyScope]) -> bool:
    """
    Check if API key has any of the required scopes

    Args:
        api_key: The API key to check
        required_scopes: List of acceptable scopes

    Returns:
        True if key has at least one scope, False otherwise
    """
    for scope in required_scopes:
        if has_scope(api_key, scope):
            return True
    return False


def has_all_scopes(api_key: APIKey, required_scopes: List[APIKeyScope]) -> bool:
    """
    Check if API key has all of the required scopes

    Args:
        api_key: The API key to check
        required_scopes: List of required scopes

    Returns:
        True if key has all scopes, False otherwise
    """
    for scope in required_scopes:
        if not has_scope(api_key, scope):
            return False
    return True


def require_scope(api_key: APIKey, required_scope: APIKeyScope) -> None:
    """
    Require a specific scope or raise HTTPException

    Args:
        api_key: The API key to check
        required_scope: The scope required

    Raises:
        HTTPException: 403 if scope not granted
    """
    if not has_scope(api_key, required_scope):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"API key does not have required scope: {required_scope.value}. "
                   f"Current scopes: {', '.join([s.value for s in api_key.scopes])}"
        )


def require_any_scope(api_key: APIKey, required_scopes: List[APIKeyScope]) -> None:
    """
    Require at least one of the specified scopes or raise HTTPException

    Args:
        api_key: The API key to check
        required_scopes: List of acceptable scopes

    Raises:
        HTTPException: 403 if none of the scopes are granted
    """
    if not has_any_scope(api_key, required_scopes):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"API key does not have any of the required scopes: "
                   f"{', '.join([s.value for s in required_scopes])}. "
                   f"Current scopes: {', '.join([s.value for s in api_key.scopes])}"
        )


def require_all_scopes(api_key: APIKey, required_scopes: List[APIKeyScope]) -> None:
    """
    Require all of the specified scopes or raise HTTPException

    Args:
        api_key: The API key to check
        required_scopes: List of required scopes

    Raises:
        HTTPException: 403 if any scope is missing
    """
    missing_scopes = [s for s in required_scopes if not has_scope(api_key, s)]

    if missing_scopes:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"API key is missing required scopes: "
                   f"{', '.join([s.value for s in missing_scopes])}. "
                   f"Current scopes: {', '.join([s.value for s in api_key.scopes])}"
        )


def get_effective_scopes(api_key: APIKey) -> List[APIKeyScope]:
    """
    Get all effective scopes for an API key (including inherited scopes)

    Args:
        api_key: The API key

    Returns:
        List of all effective scopes
    """
    effective_scopes = set(api_key.scopes)

    # Add inherited scopes from hierarchy
    for scope in api_key.scopes:
        if scope in SCOPE_HIERARCHY:
            effective_scopes.update(SCOPE_HIERARCHY[scope])

    return sorted(list(effective_scopes), key=lambda s: s.value)
