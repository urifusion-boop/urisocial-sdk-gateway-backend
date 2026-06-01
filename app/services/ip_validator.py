"""
IP whitelisting and validation
"""
import ipaddress
from typing import List, Optional
from fastapi import HTTPException, status, Request

from app.models.api_key import APIKey


def normalize_ip(ip_str: str) -> str:
    """
    Normalize IP address for consistent comparison

    Args:
        ip_str: IP address string (can be IPv4 or IPv6)

    Returns:
        Normalized IP string

    Raises:
        ValueError: If IP is invalid
    """
    try:
        ip = ipaddress.ip_address(ip_str)
        return str(ip)
    except ValueError as e:
        raise ValueError(f"Invalid IP address: {ip_str}") from e


def is_ip_in_network(ip_str: str, network_str: str) -> bool:
    """
    Check if IP is in a network (supports CIDR notation)

    Args:
        ip_str: IP address to check
        network_str: Network in CIDR notation (e.g., "192.168.1.0/24") or single IP

    Returns:
        True if IP is in network, False otherwise
    """
    try:
        ip = ipaddress.ip_address(ip_str)

        # Check if network_str is a CIDR range
        if "/" in network_str:
            network = ipaddress.ip_network(network_str, strict=False)
            return ip in network
        else:
            # Single IP comparison
            allowed_ip = ipaddress.ip_address(network_str)
            return ip == allowed_ip

    except ValueError:
        return False


def validate_ip_whitelist(ip_str: str, whitelisted_ips: List[str]) -> bool:
    """
    Check if IP is in whitelist

    Args:
        ip_str: IP address to validate
        whitelisted_ips: List of whitelisted IPs/networks

    Returns:
        True if IP is whitelisted (or whitelist is empty), False otherwise
    """
    # Empty whitelist = allow all IPs
    if not whitelisted_ips:
        return True

    # Normalize the IP
    try:
        normalized_ip = normalize_ip(ip_str)
    except ValueError:
        return False

    # Check against each whitelisted entry
    for allowed in whitelisted_ips:
        if is_ip_in_network(normalized_ip, allowed):
            return True

    return False


def get_client_ip(request: Request) -> str:
    """
    Extract client IP from request (handles proxies and load balancers)

    Args:
        request: FastAPI request object

    Returns:
        Client IP address
    """
    # Check X-Forwarded-For header (set by proxies/load balancers)
    forwarded_for = request.headers.get("X-Forwarded-For")
    if forwarded_for:
        # X-Forwarded-For can contain multiple IPs, first one is the client
        return forwarded_for.split(",")[0].strip()

    # Check X-Real-IP header (alternative proxy header)
    real_ip = request.headers.get("X-Real-IP")
    if real_ip:
        return real_ip.strip()

    # Fallback to direct client IP
    if request.client:
        return request.client.host

    return "unknown"


def require_ip_whitelist(api_key: APIKey, client_ip: str) -> None:
    """
    Require IP to be whitelisted or raise HTTPException

    Args:
        api_key: The API key with whitelist settings
        client_ip: The client's IP address

    Raises:
        HTTPException: 403 if IP is not whitelisted
    """
    if not validate_ip_whitelist(client_ip, api_key.whitelisted_ips):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"IP address {client_ip} is not whitelisted for this API key. "
                   f"Please add this IP to your whitelist or contact support."
        )


def validate_ip_format(ip_str: str) -> bool:
    """
    Validate IP address format

    Args:
        ip_str: IP address string

    Returns:
        True if valid IPv4 or IPv6, False otherwise
    """
    try:
        normalize_ip(ip_str)
        return True
    except ValueError:
        return False


def validate_cidr_format(cidr_str: str) -> bool:
    """
    Validate CIDR notation format

    Args:
        cidr_str: CIDR string (e.g., "192.168.1.0/24")

    Returns:
        True if valid CIDR, False otherwise
    """
    try:
        ipaddress.ip_network(cidr_str, strict=False)
        return True
    except ValueError:
        return False


def parse_ip_list(ip_list_str: str) -> List[str]:
    """
    Parse comma-separated IP list string into validated list

    Args:
        ip_list_str: Comma-separated IPs/CIDRs

    Returns:
        List of validated IPs/networks

    Raises:
        ValueError: If any IP is invalid
    """
    ips = [ip.strip() for ip in ip_list_str.split(",") if ip.strip()]
    validated = []

    for ip_str in ips:
        if "/" in ip_str:
            # CIDR notation
            if not validate_cidr_format(ip_str):
                raise ValueError(f"Invalid CIDR notation: {ip_str}")
        else:
            # Single IP
            if not validate_ip_format(ip_str):
                raise ValueError(f"Invalid IP address: {ip_str}")

        validated.append(ip_str)

    return validated
