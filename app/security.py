import hashlib
import ipaddress
import secrets

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError
from starlette.concurrency import run_in_threadpool

_hasher = PasswordHasher()
_DUMMY_HASH = _hasher.hash("dummy-password-for-timing")


def hash_password(password: str) -> str:
    return _hasher.hash(password)


def check_password(password: str, password_hash: str | None) -> bool:
    target = password_hash or _DUMMY_HASH
    try:
        ok = _hasher.verify(target, password)
    except (VerificationError, InvalidHashError):
        return False
    return ok and password_hash is not None


async def hash_password_async(password: str) -> str:
    # argon2 намеренно тяжелый (десятки миллисекунд процессора), в цикле событий он заблокировал бы все запросы
    return await run_in_threadpool(hash_password, password)


async def check_password_async(password: str, password_hash: str | None) -> bool:
    return await run_in_threadpool(check_password, password, password_hash)


def new_session_id() -> tuple[str, str]:
    session_id = secrets.token_urlsafe(32)
    return session_id, hash_session_id(session_id)


def hash_session_id(session_id: str) -> str:
    return hashlib.sha256(session_id.encode()).hexdigest()


def parse_networks(values: list[str]) -> list[ipaddress.IPv4Network | ipaddress.IPv6Network]:
    return [ipaddress.ip_network(value, strict=False) for value in values]


def _in(networks, address: str) -> bool:
    try:
        ip = ipaddress.ip_address(address)
    except ValueError:
        return False
    return any(ip in network for network in networks)


def resolve_client_ip(peer: str | None, forwarded_for: str | None, trusted_proxies: list[str]) -> str:
    """Адрес клиента. X-Forwarded-For учитывается, только если запрос пришел от доверенного прокси."""
    peer = peer or "unknown"
    networks = parse_networks(trusted_proxies)
    if not forwarded_for or not _in(networks, peer):
        return peer
    hops = [hop.strip() for hop in forwarded_for.split(",") if hop.strip()]
    for hop in reversed(hops):
        try:
            ipaddress.ip_address(hop)
        except ValueError:
            return peer
        if not _in(networks, hop):
            return hop
    return hops[0] if hops else peer
