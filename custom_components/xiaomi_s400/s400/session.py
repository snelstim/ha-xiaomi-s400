"""Post-login S400 session: notification wiring, CMTP reassembly and frame parsing.

Frame format and parser adapted from nokistin/xiaomi-s400-live (Apache-2.0).
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from typing import Any

from .auth import NotifyHub, login
from .crypto import SessionKeys, decrypt_cmtp, encrypt_for_device
from .miot import OP_ACTION_REPLY, OP_EVENT, MiotMessage, parse_message
from .offline import EIID_COUNT, EIID_RECORDS, SIID_OFFLINE, StoredRecord, build_request, parse_records
from .protocol import AVCTP, AVDTP, CMTP, RCV_OK, RCV_RDY, UPNP, VEND1A, VEND1C

_LOGGER = logging.getLogger(__name__)

NOTIFY_UUIDS = (UPNP, AVDTP, AVCTP, VEND1A, CMTP, VEND1C)
_DISCONNECTED = b""


@dataclass
class ScaleEvent:
    """A decoded frame from the scale."""

    type: str  # "live" | "final" | "offline_records" | "offline_count" | "action_reply" | "raw"
    weight_kg: float | None = None
    stable: bool = False
    impedance_ohm: float | None = None
    impedance_low_ohm: float | None = None
    profile_id: int | None = None
    timestamp: int | None = None
    fields: list[str] = field(default_factory=list)
    plaintext: bytes = b""
    miot: MiotMessage | None = None


def _int(value: str) -> int | None:
    value = value.strip()
    return int(value) if value.lstrip("-").isdigit() else None


def _div10(value: int | None) -> float | None:
    return value / 10 if value is not None else None


def parse_payload(plaintext: bytes) -> ScaleEvent:
    """Parse decrypted CMTP plaintext.

    Observed layout (yunmai.scales.ms104):
        LL 20 CC 00 07 08 PP 00 01 PP 00 SS a0 <ascii csv>
    Live  (2 fields):  "weight_x10,stable"
    Final (32 fields): "0,0,profile,weight_x10,stable,2,unix_ts,0..0,imp_x10,imp_low_x10"
    """
    msg = parse_message(plaintext)
    if msg is not None and msg.op == OP_ACTION_REPLY:
        return ScaleEvent(type="action_reply", plaintext=plaintext, miot=msg)
    if msg is not None and msg.op == OP_EVENT and msg.siid == SIID_OFFLINE:
        kind = {EIID_RECORDS: "offline_records", EIID_COUNT: "offline_count"}.get(msg.iid, "raw")
        return ScaleEvent(type=kind, plaintext=plaintext, miot=msg)
    idx = plaintext.find(b"\xa0")
    if idx < 0:
        return ScaleEvent(type="raw", plaintext=plaintext)
    text = plaintext[idx + 1 :].decode("ascii", errors="replace").rstrip("\x00").strip()
    parts = text.split(",")

    if len(parts) == 2:
        return ScaleEvent(
            type="live",
            weight_kg=_div10(_int(parts[0])),
            stable=parts[1].strip() == "1",
            fields=parts,
            plaintext=plaintext,
        )
    if len(parts) >= 8:
        imp = _int(parts[-2])
        imp_low = _int(parts[-1])
        return ScaleEvent(
            type="final",
            # Same layout as a stored record minus its leading field: the user is parts[1] (0 when
            # the scale didn't recognise anyone, which is always the case while we are connected).
            profile_id=_int(parts[1]) or None,
            weight_kg=_div10(_int(parts[3])),
            stable=parts[4].strip() == "1",
            timestamp=_int(parts[6]),
            impedance_ohm=_div10(imp) if imp else None,
            impedance_low_ohm=_div10(imp_low) if imp_low else None,
            fields=parts,
            plaintext=plaintext,
        )
    return ScaleEvent(type="raw", fields=parts, plaintext=plaintext)


class CmtpAssembler:
    """Reassembles multi-frame CMTP messages.

    Header: 00 00 00 SS LL 00  -> reply RCV_RDY, expect LL data frames
    Data:   NN 00 <payload>    -> after the last one reply RCV_OK
    """

    def __init__(self) -> None:
        self.expected = 0
        self.buf = b""
        self.parcel_type: int | None = None

    def feed(self, data: bytes) -> tuple[bytes | None, bytes | None]:
        """Return (ack_to_write, complete_ciphertext)."""
        if len(data) >= 6 and data[:3] == b"\x00\x00\x00" and data[5] == 0:
            self.expected = data[4]
            self.parcel_type = data[3]
            self.buf = b""
            return RCV_RDY, None
        if len(data) >= 2 and data[1] == 0 and self.expected > 0:
            self.buf += data[2:]
            if data[0] >= self.expected:
                full = self.buf
                self.expected = 0
                self.buf = b""
                return RCV_OK, full
        return None, None


class S400Session:
    """Logged-in session over an already connected Bleak-compatible client."""

    def __init__(self, client: Any, token: bytes) -> None:
        self.client = client
        self.token = token
        self.hub = NotifyHub()
        self.keys: SessionKeys | None = None
        self._assembler = CmtpAssembler()
        self._pending: list[ScaleEvent] = []
        self.disconnected = False
        self._tx_counter = 1
        self._tid = 1

    async def login(self) -> None:
        for uuid in NOTIFY_UUIDS:
            try:
                await self.client.start_notify(uuid, self.hub.make_callback(uuid))
            except Exception as err:  # noqa: BLE001 - optional characteristics
                _LOGGER.debug("subscribe %s failed (skipping): %s", uuid[4:8], err)
        await asyncio.sleep(0.3)
        self.keys = await login(self.client, self.token, self.hub)

    def mark_disconnected(self) -> None:
        self.disconnected = True
        self.hub.queue(CMTP).put_nowait(_DISCONNECTED)

    async def next_event(self, timeout: float) -> ScaleEvent | None:
        """Return the next decoded event, or None on timeout/disconnect."""
        if self._pending:
            return self._pending.pop(0)
        return await self._read_event(asyncio.get_running_loop().time() + timeout)

    async def _read_event(self, deadline: float) -> ScaleEvent | None:
        assert self.keys is not None
        q = self.hub.queue(CMTP)
        loop = asyncio.get_running_loop()
        while True:
            remaining = deadline - loop.time()
            if remaining <= 0 or self.disconnected:
                return None
            try:
                data = await asyncio.wait_for(q.get(), timeout=remaining)
            except TimeoutError:
                return None
            if data == _DISCONNECTED and self.disconnected:
                return None
            ack, full = self._assembler.feed(data)
            if ack is not None:
                await self.client.write_gatt_char(CMTP, ack, response=False)
            if full is None:
                continue
            plaintext = decrypt_cmtp(self.keys, full)
            if plaintext is None:
                _LOGGER.warning("Failed to decrypt CMTP message %s", full.hex())
                continue
            _LOGGER.debug("plaintext %s", plaintext.hex(" "))
            return parse_payload(plaintext)

    async def send(self, plaintext: bytes, timeout: float = 5.0) -> None:
        """Encrypt a MIoT message and send it as a parcel on 0x1A."""
        assert self.keys is not None
        payload = encrypt_for_device(self.keys, self._tx_counter, plaintext)
        self._tx_counter += 1
        frames = [payload[i : i + 18] for i in range(0, len(payload), 18)]
        # The parcel type for 0x1A is undocumented; reuse what the scale uses on 0x1B.
        ptype = self._assembler.parcel_type if self._assembler.parcel_type is not None else 0x00
        q = self.hub.queue(VEND1A)
        while not q.empty():
            q.get_nowait()
        _LOGGER.debug("send plaintext %s", plaintext.hex(" "))
        await self.client.write_gatt_char(VEND1A, bytes([0, 0, 0, ptype, len(frames), 0]), response=False)
        if (rdy := await asyncio.wait_for(q.get(), timeout)) != RCV_RDY:
            raise TimeoutError(f"expected RCV_RDY on 0x1A, got {rdy.hex()}")
        for n, chunk in enumerate(frames, 1):
            await self.client.write_gatt_char(VEND1A, n.to_bytes(2, "little") + chunk, response=False)
            await asyncio.sleep(0.02)
        if (ok := await asyncio.wait_for(q.get(), timeout)) != RCV_OK:
            raise TimeoutError(f"expected RCV_OK on 0x1A, got {ok.hex()}")

    async def request_offline_data(self, timeout: float = 10.0) -> list[StoredRecord]:
        """Read the weigh-ins stored on the scale without acknowledging (deleting) them.

        Other events arriving meanwhile are kept for next_event().
        """
        tid = self._tid
        self._tid = self._tid % 0xFFFF + 1
        await self.send(build_request(tid))
        loop = asyncio.get_running_loop()
        deadline = loop.time() + timeout
        expected: int | None = None
        text_parts: list[str] = []
        records: list[StoredRecord] = []
        while True:
            event = await self._read_event(deadline)
            if event is None:
                break
            if event.type == "action_reply":
                if event.miot and event.miot.code:
                    raise RuntimeError(f"request-offline-data failed: {event.miot.code}")
            elif event.type == "offline_count":
                expected = event.miot.values.get(3) if event.miot else None
                if expected == 0:
                    break
            elif event.type == "offline_records":
                text_parts.append(str(event.miot.values.get(1, "")) if event.miot else "")
                records = parse_records("_".join(text_parts))
                if expected is None or len(records) >= expected:
                    # Without a count, give further record events a short chance to arrive.
                    deadline = min(deadline, loop.time() + (1.5 if expected is None else 0))
            else:
                self._pending.append(event)
        _LOGGER.debug("Stored records: expected=%s parsed=%d", expected, len(records))
        return records
