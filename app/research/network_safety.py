import asyncio
import ipaddress
import socket
from collections.abc import Awaitable, Callable
from urllib.parse import urlsplit, urlunsplit

AddressResolver = Callable[[str], Awaitable[list[str]]]


async def resolve_addresses(hostname: str) -> list[str]:
    records = await asyncio.to_thread(
        socket.getaddrinfo,
        hostname,
        None,
        type=socket.SOCK_STREAM,
    )
    return list({record[4][0] for record in records})


def normalize_http_url(url: str) -> str | None:
    parsed = urlsplit(url.strip())
    try:
        parsed.port
    except ValueError:
        return None
    if (
        parsed.scheme.lower() not in {"http", "https"}
        or not parsed.hostname
        or parsed.username
        or parsed.password
    ):
        return None
    return urlunsplit(
        (
            parsed.scheme.lower(),
            parsed.netloc.lower(),
            parsed.path or "/",
            parsed.query,
            "",
        )
    )


async def public_url_error(
    url: str,
    resolver: AddressResolver = resolve_addresses,
) -> str | None:
    normalized = normalize_http_url(url)
    if normalized is None:
        return "unsafe_url"

    hostname = urlsplit(normalized).hostname
    assert hostname is not None
    try:
        addresses = [str(ipaddress.ip_address(hostname))]
    except ValueError:
        try:
            addresses = await resolver(hostname)
        except (OSError, socket.gaierror):
            return "dns_resolution_failed"

    if not addresses:
        return "dns_resolution_failed"
    try:
        if any(not ipaddress.ip_address(address).is_global for address in addresses):
            return "unsafe_url"
    except ValueError:
        return "dns_resolution_failed"
    return None
