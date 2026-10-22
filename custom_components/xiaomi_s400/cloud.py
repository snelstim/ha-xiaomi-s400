"""Xiaomi cloud QR login and device key lookup, so the token and BLE key needn't be extracted by hand.

Async port of the QR-code flow in PiotrMachowski/Xiaomi-cloud-tokens-extractor (MIT).
"""

from __future__ import annotations

import asyncio
import base64
import hashlib
import json
import logging
import os
import random
import string
import time
from dataclasses import dataclass
from typing import Any

import aiohttp

_LOGGER = logging.getLogger(__name__)

SERVERS = ["cn", "de", "us", "ru", "tw", "sg", "in", "i2"]
POLL_TIMEOUT = 30


class CloudError(Exception):
    """Xiaomi cloud request failed."""


@dataclass
class CloudDevice:
    name: str
    model: str
    mac: str
    token: str | None
    bindkey: str | None


def _rc4(key: bytes, data: bytes) -> bytes:
    """RC4 with the first 1024 keystream bytes dropped, as the Xiaomi API expects."""
    s = list(range(256))
    j = 0
    for i in range(256):
        j = (j + s[i] + key[i % len(key)]) % 256
        s[i], s[j] = s[j], s[i]
    i = j = 0
    out = bytearray()
    for n, byte in enumerate(bytes(1024) + data):
        i = (i + 1) % 256
        j = (j + s[i]) % 256
        s[i], s[j] = s[j], s[i]
        if n >= 1024:
            out.append(byte ^ s[(s[i] + s[j]) % 256])
    return bytes(out)


def _loads(text: str) -> dict[str, Any]:
    return json.loads(text.replace("&&&START&&&", ""))


class XiaomiCloud:
    """One QR login session against account.xiaomi.com."""

    def __init__(self, session: aiohttp.ClientSession) -> None:
        self._session = session
        agent_id = "".join(random.choices("ABCDE", k=13))
        self._agent = f"{''.join(random.choices(string.ascii_lowercase, k=18))}-{agent_id} APP/com.xiaomi.mihome APPV/10.5.201"
        self.qr_image_url = ""
        self.login_url = ""
        self._lp_url = ""
        self._timeout = 300.0
        self._user_id: str | None = None
        self._ssecurity: str | None = None
        self._service_token: str | None = None

    async def start_qr_login(self) -> None:
        params = {
            "_qrsize": "480",
            "qs": "%3Fsid%3Dxiaomiio%26_json%3Dtrue",
            "callback": "https://sts.api.io.mi.com/sts",
            "_hasLogo": "false",
            "sid": "xiaomiio",
            "serviceParam": "",
            "_locale": "en_GB",
            "_dc": str(int(time.time() * 1000)),
        }
        async with self._session.get("https://account.xiaomi.com/longPolling/loginUrl", params=params) as resp:
            if resp.status != 200:
                raise CloudError(f"loginUrl HTTP {resp.status}")
            data = _loads(await resp.text())
        if "qr" not in data:
            raise CloudError("no QR code in loginUrl response")
        self.qr_image_url = data["qr"]
        self.login_url = data["loginUrl"]
        self._lp_url = data["lp"]
        self._timeout = float(data.get("timeout", 300))

    async def wait_for_scan(self) -> None:
        """Long-poll until the QR code is scanned and approved in the Xiaomi Home app."""
        deadline = time.monotonic() + self._timeout
        while True:
            try:
                async with self._session.get(
                    self._lp_url, timeout=aiohttp.ClientTimeout(total=None, sock_read=POLL_TIMEOUT)
                ) as resp:
                    text = await resp.text()
                    _LOGGER.debug("QR long-poll: HTTP %s, %d bytes", resp.status, len(text))
                    if resp.status == 200:
                        data = _loads(text)
                        break
            except TimeoutError:
                _LOGGER.debug("QR long-poll: no answer yet")
            if time.monotonic() > deadline:
                raise CloudError("QR code expired")
            await asyncio.sleep(1)
        self._user_id = str(data["userId"])
        self._ssecurity = data["ssecurity"]
        async with self._session.get(
            data["location"], headers={"content-type": "application/x-www-form-urlencoded"}
        ) as resp:
            if resp.status != 200:
                raise CloudError(f"service token HTTP {resp.status}")
            cookie = resp.cookies.get("serviceToken")
        if cookie is None:
            cookie = next((c for c in self._session.cookie_jar if c.key == "serviceToken"), None)
        if cookie is None:
            raise CloudError("no service token")
        self._service_token = cookie.value

    # ---- signed + RC4 encrypted API --------------------------------------

    def _signed_nonce(self, nonce: str) -> str:
        assert self._ssecurity
        digest = hashlib.sha256(base64.b64decode(self._ssecurity) + base64.b64decode(nonce)).digest()
        return base64.b64encode(digest).decode()

    @staticmethod
    def _enc_signature(path: str, signed_nonce: str, params: dict[str, str]) -> str:
        parts = ["POST", path, *(f"{k}={v}" for k, v in params.items()), signed_nonce]
        return base64.b64encode(hashlib.sha1("&".join(parts).encode()).digest()).decode()

    async def _call(self, server: str, path: str, data: dict[str, Any]) -> dict[str, Any] | None:
        url = "https://" + ("" if server == "cn" else f"{server}.") + "api.io.mi.com/app" + path
        nonce = base64.b64encode(os.urandom(8) + int(time.time() / 60).to_bytes(4, "big")).decode()
        signed_nonce = self._signed_nonce(nonce)
        key = base64.b64decode(signed_nonce)
        params = {"data": json.dumps(data, separators=(",", ":"))}
        params["rc4_hash__"] = self._enc_signature(path, signed_nonce, params)
        params = {k: base64.b64encode(_rc4(key, v.encode())).decode() for k, v in params.items()}
        params["signature"] = self._enc_signature(path, signed_nonce, params)
        params["ssecurity"] = self._ssecurity or ""
        params["_nonce"] = nonce
        headers = {
            "Accept-Encoding": "identity",
            "User-Agent": self._agent,
            "Content-Type": "application/x-www-form-urlencoded",
            "x-xiaomi-protocal-flag-cli": "PROTOCAL-HTTP2",
            "MIOT-ENCRYPT-ALGORITHM": "ENCRYPT-RC4",
        }
        cookies = {
            "userId": str(self._user_id),
            "yetAnotherServiceToken": str(self._service_token),
            "serviceToken": str(self._service_token),
            "locale": "en_GB",
            "channel": "MI_APP_STORE",
        }
        async with self._session.post(url, headers=headers, cookies=cookies, params=params) as resp:
            if resp.status != 200:
                _LOGGER.debug("%s %s: HTTP %s", server, path, resp.status)
                return None
            text = await resp.text()
        try:
            return json.loads(_rc4(key, base64.b64decode(text)))
        except ValueError:
            _LOGGER.debug("%s %s: undecodable response", server, path)
            return None

    async def find_devices(self, servers: list[str] | None = None) -> list[CloudDevice]:
        """List devices (own and shared homes) on all servers, with BLE keys for Bluetooth devices."""
        found: list[CloudDevice] = []
        for server in servers or SERVERS:
            homes: list[tuple[Any, Any]] = []
            res = await self._call(server, "/v2/homeroom/gethome", {
                "fg": True, "fetch_share": True, "fetch_share_dev": True, "limit": 300, "app_ver": 7,
            })
            for h in ((res or {}).get("result") or {}).get("homelist") or []:
                homes.append((h["id"], self._user_id))
            res = await self._call(server, "/v2/user/get_device_cnt", {"fetch_own": True, "fetch_share": True})
            for h in (((res or {}).get("result") or {}).get("share") or {}).get("share_family") or []:
                homes.append((h["home_id"], h["home_owner"]))
            for home_id, owner in homes:
                res = await self._call(server, "/v2/home/home_device_list", {
                    "home_owner": int(owner), "home_id": int(home_id), "limit": 200,
                    "get_split_device": True, "support_smart_home": True,
                })
                for dev in ((res or {}).get("result") or {}).get("device_info") or []:
                    bindkey = None
                    did = str(dev.get("did", ""))
                    if "blt" in did:
                        key = await self._call(server, "/v2/device/blt_get_beaconkey", {"did": did, "pdid": 1})
                        bindkey = ((key or {}).get("result") or {}).get("beaconkey")
                    found.append(CloudDevice(
                        name=dev.get("name", ""),
                        model=dev.get("model", ""),
                        mac=str(dev.get("mac", "")).upper(),
                        token=dev.get("token"),
                        bindkey=bindkey,
                    ))
        return found
