"""Decrypt S400 MiBeacon v4/v5 advertisements (only to read heart rate).

Layout per Bluetooth-Devices/xiaomi-ble (Apache-2.0) and the ESPHome xiaomi_body_scale docs.
"""

from __future__ import annotations

import struct
from dataclasses import dataclass

from cryptography.hazmat.primitives.ciphers.aead import AESCCM

S400_OBJECT = 0x6E16


@dataclass(frozen=True)
class AdvReading:
    """Decoded 0x6E16 object."""

    profile_id: int
    weight_kg: float | None
    heart_rate: int | None
    impedance_ohm: float | None
    frame_counter: int
    timestamp: int = 0


def decode_advertisement(service_data: bytes, mac: str, bindkey: bytes) -> AdvReading | None:
    """Return the S400 reading from FE95 service data, or None if not applicable."""
    data = service_data
    if len(data) < 5:
        return None
    frctrl = data[0] | (data[1] << 8)
    version = frctrl >> 12
    if not (frctrl >> 6) & 1 or not (frctrl >> 3) & 1 or version < 4:
        return None  # no object, not encrypted, or legacy scheme

    i = 5
    mac_bytes = bytes.fromhex(mac.replace(":", ""))
    if (frctrl >> 4) & 1:
        i += 6
    if (frctrl >> 5) & 1:
        i += 1
        if len(data) < i:
            return None
        if data[i - 1] & 0x20:
            i += 1
    if len(data) < i + 9:
        return None

    nonce = mac_bytes[::-1] + data[2:5] + data[-7:-4]
    try:
        payload = AESCCM(bindkey, tag_length=4).decrypt(nonce, data[i:-7] + data[-4:], b"\x11")
    except Exception:  # noqa: BLE001 - wrong key or corrupted frame
        return None

    while len(payload) >= 3:
        obj_type = payload[0] | (payload[1] << 8)
        length = payload[2]
        obj = payload[3 : 3 + length]
        payload = payload[3 + length :]
        if obj_type != S400_OBJECT or len(obj) < 9:
            continue
        profile_id, packed, ts = struct.unpack("<BII", obj[:9])
        mass = packed & 0x7FF
        hr = (packed >> 11) & 0x7F
        imp = packed >> 18
        return AdvReading(
            profile_id=profile_id,
            weight_kg=mass / 10 if mass else None,
            heart_rate=hr + 50 if 0 < hr < 127 else None,
            impedance_ohm=imp / 10 if imp else None,
            frame_counter=data[4],
            timestamp=ts,
        )
    return None


def encrypt_advertisement(obj: bytes, mac: str, bindkey: bytes, product_id: int = 0x30D9, counter: int = 1) -> bytes:
    """Build an encrypted MiBeacon v5 frame (used by tests)."""
    frctrl = 0x5948  # v5, object include, encrypted, registered
    header = struct.pack("<HHB", frctrl, product_id, counter)
    ext = b"\x00\x00\x01"
    nonce = bytes.fromhex(mac.replace(":", ""))[::-1] + header[2:5] + ext
    ct = AESCCM(bindkey, tag_length=4).encrypt(nonce, obj, b"\x11")
    return header + ct[:-4] + ext + ct[-4:]
