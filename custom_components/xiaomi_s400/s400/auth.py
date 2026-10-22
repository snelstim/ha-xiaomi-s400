"""Mi Home v2 BLE LOGIN handshake.

Adapted from nokistin/xiaomi-s400-live (Apache-2.0), which builds on
dnandha/miauth (Apache-2.0). Changes: decoupled from a concrete BleakClient
so it works with Home Assistant's Bluetooth stack (incl. ESPHome proxies).
"""

from __future__ import annotations

import asyncio
import logging
import secrets
from collections.abc import Callable
from typing import Any

from .crypto import SessionKeys, derive_login_keys, hmac_sha256
from .protocol import (
    AVDTP,
    CFM_LOGIN_OK,
    CMD_LOGIN,
    CMD_SEND_INFO,
    CMD_SEND_KEY,
    RCV_OK,
    RCV_RDY,
    UPNP,
)

_LOGGER = logging.getLogger(__name__)


class AuthError(Exception):
    """Login handshake failed."""


class BadTokenError(AuthError):
    """HMAC verification failed: token is wrong or has rotated."""


class NotifyHub:
    """Routes GATT notifications into per-characteristic asyncio queues."""

    def __init__(self) -> None:
        self.queues: dict[str, asyncio.Queue[bytes]] = {}

    def queue(self, uuid: str) -> asyncio.Queue[bytes]:
        if uuid not in self.queues:
            self.queues[uuid] = asyncio.Queue()
        return self.queues[uuid]

    def make_callback(self, uuid: str) -> Callable[[Any, bytearray], None]:
        q = self.queue(uuid)

        def _cb(_sender: Any, data: bytearray) -> None:
            _LOGGER.debug("<- %s %s", uuid[4:8], bytes(data).hex(" "))
            q.put_nowait(bytes(data))

        return _cb


async def _wait(q: asyncio.Queue[bytes], timeout: float) -> bytes:
    return await asyncio.wait_for(q.get(), timeout=timeout)


async def _write(client: Any, uuid: str, data: bytes) -> None:
    _LOGGER.debug("-> %s %s", uuid[4:8], data.hex(" "))
    await client.write_gatt_char(uuid, data, response=False)


async def _write_parcel(
    client: Any, uuid: str, data: bytes, chunk_size: int = 18, frame_delay: float = 0.05
) -> None:
    for i in range(0, len(data), chunk_size):
        chunk = data[i : i + chunk_size]
        n = i // chunk_size + 1
        await _write(client, uuid, bytes([n & 0xFF, (n >> 8) & 0xFF]) + chunk)
        await asyncio.sleep(frame_delay)


async def _recv_multiframe(client: Any, q: asyncio.Queue[bytes], timeout: float) -> bytes:
    first = await _wait(q, timeout)
    if len(first) < 6 or first[:3] != b"\x00\x00\x00":
        raise AuthError(f"unexpected first frame: {first.hex()}")
    expected = first[4] | (first[5] << 8)
    await _write(client, AVDTP, RCV_RDY)
    buf = b""
    for _ in range(expected):
        frame = await _wait(q, timeout)
        buf += frame[2:]
    await _write(client, AVDTP, RCV_OK)
    return buf


async def login(client: Any, token: bytes, hub: NotifyHub, timeout: float = 8.0) -> SessionKeys:
    """Run Mi Home v2 LOGIN. Notifications on UPNP and AVDTP must already route into hub."""
    if len(token) != 12:
        raise AuthError(f"token must be 12 bytes, got {len(token)}")

    avdtp_q = hub.queue(AVDTP)
    upnp_q = hub.queue(UPNP)
    app_rand = secrets.token_bytes(16)

    await _write(client, UPNP, CMD_LOGIN)
    await _write(client, AVDTP, CMD_SEND_KEY)
    if (rdy := await _wait(avdtp_q, timeout)) != RCV_RDY:
        raise AuthError(f"expected RCV_RDY after CMD_SEND_KEY, got {rdy.hex()}")
    await _write_parcel(client, AVDTP, app_rand)
    if (ok := await _wait(avdtp_q, timeout)) != RCV_OK:
        raise AuthError(f"expected RCV_OK, got {ok.hex()}")

    dev_rand = await _recv_multiframe(client, avdtp_q, timeout)
    if len(dev_rand) != 16:
        raise AuthError(f"bad device rand length {len(dev_rand)}")
    remote_info = await _recv_multiframe(client, avdtp_q, timeout)

    keys = derive_login_keys(token, app_rand, dev_rand)
    if remote_info != hmac_sha256(keys.dev_key, dev_rand + app_rand):
        raise BadTokenError("HMAC mismatch: token is wrong or has rotated")

    our_info = hmac_sha256(keys.app_key, app_rand + dev_rand)
    await _write(client, AVDTP, CMD_SEND_INFO)
    if (rdy := await _wait(avdtp_q, timeout)) != RCV_RDY:
        raise AuthError(f"expected RCV_RDY for SEND_INFO, got {rdy.hex()}")
    await _write_parcel(client, AVDTP, our_info)
    if (ok := await _wait(avdtp_q, timeout)) != RCV_OK:
        raise AuthError(f"expected RCV_OK for SEND_INFO, got {ok.hex()}")

    if (result := await _wait(upnp_q, timeout)) != CFM_LOGIN_OK:
        raise AuthError(f"login rejected: {result.hex()}")
    return keys
