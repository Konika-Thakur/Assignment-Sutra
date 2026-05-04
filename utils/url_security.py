import ipaddress
import socket
from urllib.parse import urlparse


PRIVATE_HOST_ERROR = "URL host resolves to a private, local, or otherwise unsafe address."


def assert_safe_url(url, allow_local=False):
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        raise ValueError("Only http and https URLs are allowed.")
    if not parsed.hostname:
        raise ValueError("URL must include a hostname.")

    try:
        addr_infos = socket.getaddrinfo(parsed.hostname, None)
    except socket.gaierror as exc:
        raise ValueError(f"Could not resolve URL host: {parsed.hostname}") from exc

    for addr_info in addr_infos:
        ip = ipaddress.ip_address(addr_info[4][0])
        if allow_local and (ip.is_private or ip.is_loopback):
            continue
        if (
            ip.is_private
            or ip.is_loopback
            or ip.is_link_local
            or ip.is_multicast
            or ip.is_reserved
            or ip.is_unspecified
        ):
            raise ValueError(PRIVATE_HOST_ERROR)

    return url
