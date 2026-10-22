"""MIoT-spec-over-BLE messages carried inside the encrypted 0x1A / 0x1B parcels.

message = u16 (0x2 << 12 | total length) . u16 tid . u8 op . body   (little endian)
    op 0x02 get_properties   count, (siid u8, piid u16)*
    op 0x03   reply          count, (siid, piid, code i16, tl, value)*
    op 0x05 action           siid u8, aiid u16, argc u8, (piid u16, tl, value)*
    op 0x06   reply          code i16
    op 0x07 event            siid u8, eiid u16, argc u8, (piid u16, tl, value)*
tl = u16 (type << 12 | value length); type 1 = uint8, 5 = uint32, 0xA = string.
"""

from __future__ import annotations

import struct
from dataclasses import dataclass, field
from typing import Any

OP_ACTION = 0x05
OP_ACTION_REPLY = 0x06
OP_EVENT = 0x07

TYPE_UINT8 = 0x1
TYPE_UINT32 = 0x5
TYPE_STRING = 0xA


@dataclass
class MiotMessage:
    """A decoded MIoT message."""

    op: int
    tid: int
    siid: int | None = None
    iid: int | None = None  # aiid / eiid
    code: int | None = None
    values: dict[int, Any] = field(default_factory=dict)  # piid -> value


def _encode_value(type_: int, value: Any) -> bytes:
    if type_ == TYPE_UINT8:
        raw = bytes([value])
    elif type_ == TYPE_UINT32:
        raw = struct.pack("<I", value)
    elif type_ == TYPE_STRING:
        raw = value.encode()
    else:
        raw = bytes(value)
    return struct.pack("<H", type_ << 12 | len(raw)) + raw


def _decode_value(type_: int, raw: bytes) -> Any:
    if type_ == TYPE_STRING:
        return raw.decode("ascii", errors="replace").rstrip("\x00")
    if type_ in (TYPE_UINT8, TYPE_UINT32) or len(raw) in (1, 2, 4):
        return int.from_bytes(raw, "little")
    return raw


def build_action(tid: int, siid: int, aiid: int, args: list[tuple[int, int, Any]]) -> bytes:
    """Build an action request; args are (piid, type, value)."""
    body = bytes([OP_ACTION, siid]) + struct.pack("<HB", aiid, len(args))
    for piid, type_, value in args:
        body += struct.pack("<H", piid) + _encode_value(type_, value)
    total = 4 + len(body)
    return struct.pack("<HH", 0x2 << 12 | total, tid) + body


def parse_message(data: bytes) -> MiotMessage | None:
    """Decode a MIoT message, or None if it doesn't look like one."""
    if len(data) < 5 or data[1] >> 4 != 0x2:
        return None
    _, tid, op = struct.unpack_from("<HHB", data)
    msg = MiotMessage(op=op, tid=tid)
    try:
        if op == OP_ACTION_REPLY:
            (msg.code,) = struct.unpack_from("<h", data, 5)
        elif op == OP_EVENT:
            msg.siid, msg.iid, argc = struct.unpack_from("<BHB", data, 5)
            pos = 9
            for _ in range(argc):
                piid, tl = struct.unpack_from("<HH", data, pos)
                pos += 4
                length = tl & 0x0FFF
                msg.values[piid] = _decode_value(tl >> 12, data[pos : pos + length])
                pos += length
    except struct.error:
        return None
    return msg
