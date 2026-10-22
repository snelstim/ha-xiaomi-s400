"""In-memory fake of the S400 GATT side, implementing the device half of Mi Home v2 LOGIN."""

from __future__ import annotations

import asyncio
import secrets
from collections.abc import Callable
from typing import Any

from cryptography.hazmat.primitives.ciphers.aead import AESCCM

from custom_components.xiaomi_s400.s400.crypto import derive_login_keys, hmac_sha256
from custom_components.xiaomi_s400.s400.protocol import (
    AVDTP,
    CFM_LOGIN_ERR,
    CFM_LOGIN_OK,
    CMD_LOGIN,
    CMD_SEND_INFO,
    CMD_SEND_KEY,
    CMTP,
    RCV_OK,
    RCV_RDY,
    UPNP,
    VEND1A,
)


def frames(payload: bytes, chunk: int = 18) -> list[bytes]:
    out = []
    for i in range(0, len(payload), chunk):
        n = i // chunk + 1
        out.append(bytes([n & 0xFF, n >> 8]) + payload[i : i + chunk])
    return out


def csv_plaintext(csv: str) -> bytes:
    body = csv.encode()
    return bytes([len(body) + 12]) + bytes.fromhex("20cc00070801000101000a") + b"\xa0" + body


def miot_event(siid: int, eiid: int, piid: int, value: bytes, type_: int) -> bytes:
    body = bytes([0x07, siid, eiid, 0, 1]) + piid.to_bytes(2, "little")
    body += (type_ << 12 | len(value)).to_bytes(2, "little") + value
    return (0x2000 | (4 + len(body))).to_bytes(2, "little") + b"\x01\x00" + body


class FakeScale:
    """Bleak-client-like object. Notifications are delivered via the event loop."""

    def __init__(self, token: bytes) -> None:
        self.token = token
        self.callbacks: dict[str, Callable[[Any, bytearray], None]] = {}
        self.state = "idle"
        self.app_rand = b""
        self.dev_rand = secrets.token_bytes(16)
        self.keys = None
        self.iter = 0
        self.cmtp_out: list[bytes] = []
        self.writes: list[tuple[str, bytes]] = []
        self.login_ok = False
        self.app_in: list[bytes] = []  # decrypted messages written by the app on 0x1A
        self._rx_expected = 0
        self._rx_buf = b""
        self.stored: str = ""  # records string returned by request-offline-data
        self.on_message: Callable[[bytes], None] | None = self._answer_offline

    async def start_notify(self, uuid: str, cb: Callable[[Any, bytearray], None]) -> None:
        self.callbacks[uuid] = cb

    def _notify(self, uuid: str, data: bytes) -> None:
        asyncio.get_running_loop().call_soon(self.callbacks[uuid], None, bytearray(data))

    async def write_gatt_char(self, uuid: str, data: bytes, response: bool = False) -> None:
        data = bytes(data)
        self.writes.append((uuid, data))
        if uuid == UPNP and data == CMD_LOGIN:
            self.state = "login"
        elif uuid == AVDTP and data == CMD_SEND_KEY:
            self.state = "recv_key"
            self._notify(AVDTP, RCV_RDY)
        elif uuid == AVDTP and self.state == "recv_key" and data[:2] == b"\x01\x00":
            self.app_rand = data[2:]
            self._notify(AVDTP, RCV_OK)
            self.state = "send_rand_hdr"
            self._notify(AVDTP, b"\x00\x00\x00\x0d\x01\x00")
        elif uuid == AVDTP and data == RCV_RDY and self.state == "send_rand_hdr":
            for f in frames(self.dev_rand):
                self._notify(AVDTP, f)
            self.state = "send_rand_wait_ok"
        elif uuid == AVDTP and data == RCV_OK and self.state == "send_rand_wait_ok":
            self.keys = derive_login_keys(self.token, self.app_rand, self.dev_rand)
            # Device always computes with its real token; a wrong app token then fails HMAC.
            self.remote_info = hmac_sha256(self.keys.dev_key, self.dev_rand + self.app_rand)
            self.state = "send_info_hdr"
            self._notify(AVDTP, b"\x00\x00\x00\x0c\x02\x00")
        elif uuid == AVDTP and data == RCV_RDY and self.state == "send_info_hdr":
            for f in frames(self.remote_info):
                self._notify(AVDTP, f)
            self.state = "send_info_wait_ok"
        elif uuid == AVDTP and data == RCV_OK and self.state == "send_info_wait_ok":
            self.state = "await_app_info"
        elif uuid == AVDTP and data == CMD_SEND_INFO:
            self.app_info = b""
            self._notify(AVDTP, RCV_RDY)
        elif uuid == AVDTP and self.state == "await_app_info" and data[1] == 0 and data[0] in (1, 2):
            self.app_info += data[2:]
            if len(self.app_info) >= 32:
                self._notify(AVDTP, RCV_OK)
                expected = hmac_sha256(self.keys.app_key, self.app_rand + self.dev_rand)
                self.login_ok = self.app_info == expected
                self._notify(UPNP, CFM_LOGIN_OK if self.login_ok else CFM_LOGIN_ERR)
                self.state = "ready"
        elif uuid == VEND1A and len(data) == 6 and data[:3] == b"\x00\x00\x00":
            self._rx_expected = data[4]
            self._rx_buf = b""
            self._notify(VEND1A, RCV_RDY)
        elif uuid == VEND1A and self._rx_expected:
            self._rx_buf += data[2:]
            if data[0] == self._rx_expected:
                self._rx_expected = 0
                self._notify(VEND1A, RCV_OK)
                it, ct = self._rx_buf[:2], self._rx_buf[2:]
                nonce = self.keys.app_iv + bytes(4) + it + bytes(2)
                msg = AESCCM(self.keys.app_key, tag_length=4).decrypt(nonce, ct, None)
                self.app_in.append(msg)
                if self.on_message:
                    self.on_message(msg)
        elif uuid == CMTP and data == RCV_RDY and self.cmtp_out:
            for f in frames(self.cmtp_out[0]):
                self._notify(CMTP, f)
        elif uuid == CMTP and data == RCV_OK and self.cmtp_out:
            self.cmtp_out.pop(0)
            self._send_header()

    def _send_header(self) -> None:
        if self.cmtp_out:
            self._notify(CMTP, bytes([0, 0, 0, 0x06, len(frames(self.cmtp_out[0])), 0]))

    def _answer_offline(self, msg: bytes) -> None:
        if msg[4:6] != b"\x05\x09":
            return
        tid = msg[2:4]
        self.send_plaintext(b"\x07\x20" + tid + b"\x06\x00\x00")
        count = self.stored.count("_") + 1 if self.stored else 0
        self.send_plaintext(miot_event(9, 2, 3, bytes([count]), 0x1))
        if self.stored:
            self.send_plaintext(miot_event(9, 1, 1, self.stored.encode(), 0xA))

    def send_csv(self, csv: str) -> None:
        self.send_plaintext(csv_plaintext(csv))

    def send_plaintext(self, plaintext: bytes) -> None:
        """Encrypt and push a CMTP message (header first; frames after RCV_RDY)."""
        assert self.keys is not None
        it = self.iter.to_bytes(2, "little")
        self.iter += 1
        nonce = self.keys.dev_iv + bytes(4) + it + bytes(2)
        ct = it + AESCCM(self.keys.dev_key, tag_length=4).encrypt(nonce, plaintext, None)
        self.cmtp_out.append(ct)
        if len(self.cmtp_out) == 1:
            self._send_header()
