import ipaddress
import os
import socket
from urllib.parse import urlsplit


def validate_configured_target(
    base_url: str,
    allowed_hosts: set[str],
    path: str,
    private_hosts_env: str = "REPLAY_ALLOWED_PRIVATE_HOSTS",
) -> str:
    base_url = base_url.rstrip("/")
    allowed_hosts = {host.strip().lower() for host in allowed_hosts if host.strip()}
    private_hosts = {
        host.strip().lower()
        for host in os.environ.get(private_hosts_env, "").split(",")
        if host.strip()
    }
    parsed = urlsplit(base_url)
    if not parsed.hostname or parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise ValueError("Replay target URL is malformed")
    hostname = parsed.hostname.lower()
    if hostname not in allowed_hosts:
        raise ValueError("Replay target host is not in REPLAY_ALLOWED_HOSTS")
    if parsed.scheme != "https" and not (
        parsed.scheme == "http"
        and (
            os.environ.get("APP_ENV") == "development"
            or hostname in private_hosts
        )
    ):
        raise ValueError("Replay target must use HTTPS except for explicitly allowlisted private services")
    try:
        addresses = {ipaddress.ip_address(hostname)}
    except ValueError:
        addresses = {
            ipaddress.ip_address(result[4][0])
            for result in socket.getaddrinfo(hostname, parsed.port or (443 if parsed.scheme == "https" else 80))
        }
    allow_private = (
        os.environ.get("APP_ENV") == "development"
        and os.environ.get("REPLAY_ALLOW_PRIVATE_TARGETS") == "true"
    ) or hostname in private_hosts
    if not allow_private and any(not address.is_global for address in addresses):
        raise ValueError("Replay target resolves to a non-public network address")
    if not path.startswith("/") or path.startswith("//") or any(
        segment in {".", ".."} for segment in path.split("/")
    ):
        raise ValueError("Replay path is not safe")
    return f"{base_url}{path}"


def validated_target(path: str) -> str:
    allowed_hosts = {
        host.strip().lower()
        for host in os.environ.get("REPLAY_ALLOWED_HOSTS", "").split(",")
        if host.strip()
    }
    return validate_configured_target(
        os.environ.get("REPLAY_TARGET_URL", ""),
        allowed_hosts,
        path,
    )
