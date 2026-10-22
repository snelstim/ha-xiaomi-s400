"""Home Assistant level tests: config flow, subentries, entities fed by the fake scale."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from homeassistant.config_entries import SOURCE_USER, ConfigSubentryData
from homeassistant.const import CONF_ADDRESS, CONF_NAME
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.xiaomi_s400.const import (
    CONF_BIRTHDAY,
    CONF_HEIGHT,
    CONF_PROFILE_ID,
    CONF_SEX,
    CONF_TOKEN,
    DOMAIN,
    EVENT_MEASUREMENT,
)

from .fake_scale import FakeScale

ADDRESS = "AA:BB:CC:DD:EE:FF"
TOKEN_HEX = "00112233445566778899aabb"
FINAL_ASIA = "0,0,2,612,1,2,1760607000," + ",".join(["0"] * 23) + ",5650,5120"
FINAL_DAVE = "0,0,1,909,1,2,1760607100," + ",".join(["0"] * 23) + ",4890,4413"


@pytest.fixture(autouse=True)
def no_bluetooth():
    """Stub HA bluetooth so tests don't need a real adapter."""
    with (
        patch("custom_components.xiaomi_s400.coordinator.bluetooth.async_register_callback", return_value=lambda: None),
        patch("custom_components.xiaomi_s400.config_flow.async_discovered_service_info", return_value=[]),
    ):
        yield


async def test_user_flow(hass: HomeAssistant) -> None:
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": SOURCE_USER})
    assert result["type"] is FlowResultType.FORM

    result = await hass.config_entries.flow.async_configure(result["flow_id"], {CONF_ADDRESS: "bad"})
    assert result["errors"] == {CONF_ADDRESS: "invalid_mac"}

    result = await hass.config_entries.flow.async_configure(result["flow_id"], {CONF_ADDRESS: ADDRESS.lower()})
    assert result["type"] is FlowResultType.MENU
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {"next_step_id": "credentials"})
    assert result["step_id"] == "credentials"

    result = await hass.config_entries.flow.async_configure(result["flow_id"], {CONF_TOKEN: "zz"})
    assert result["errors"] == {CONF_TOKEN: "invalid_token"}

    with patch("custom_components.xiaomi_s400.async_setup_entry", return_value=True):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {CONF_TOKEN: TOKEN_HEX.upper(), CONF_NAME: "Waga"}
        )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["data"] == {CONF_ADDRESS: ADDRESS, CONF_NAME: "Waga", CONF_TOKEN: TOKEN_HEX, "bindkey": None}


async def test_cloud_login_flow(hass: HomeAssistant) -> None:
    from custom_components.xiaomi_s400.cloud import CloudDevice

    scanned = asyncio.Event()

    class FakeCloud:
        qr_image_url = "https://example.invalid/qr.png"
        login_url = "https://example.invalid/login"

        def __init__(self, _session) -> None:
            pass

        async def start_qr_login(self) -> None:
            pass

        async def wait_for_scan(self) -> None:
            await scanned.wait()

        async def find_devices(self, servers=None):
            return [
                CloudDevice("Lamp", "yeelink.light", "11:22:33:44:55:66", "a" * 32, None),
                CloudDevice("Body Shamer", "yunmai.scales.ms104", ADDRESS, TOKEN_HEX, "ab" * 16),
            ]

    with patch("custom_components.xiaomi_s400.config_flow.XiaomiCloud", FakeCloud):
        result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": SOURCE_USER})
        result = await hass.config_entries.flow.async_configure(result["flow_id"], {CONF_ADDRESS: ADDRESS})
        result = await hass.config_entries.flow.async_configure(result["flow_id"], {"next_step_id": "cloud"})
        assert result["type"] is FlowResultType.SHOW_PROGRESS
        assert result["description_placeholders"]["qr"] == FakeCloud.qr_image_url
        scanned.set()
        await hass.async_block_till_done()
        result = await hass.config_entries.flow.async_configure(result["flow_id"])
        assert result["type"] is FlowResultType.FORM and result["step_id"] == "credentials"
        assert not result["errors"]
        with patch("custom_components.xiaomi_s400.async_setup_entry", return_value=True):
            result = await hass.config_entries.flow.async_configure(
                result["flow_id"], {CONF_TOKEN: TOKEN_HEX, "bindkey": "ab" * 16, CONF_NAME: "Body Shamer"}
            )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["data"]["token"] == TOKEN_HEX and result["data"]["bindkey"] == "ab" * 16


def test_cloud_rc4_roundtrip() -> None:
    from custom_components.xiaomi_s400.cloud import _rc4

    assert _rc4(b"key", _rc4(b"key", b"hello")) == b"hello"


def _entry(persons: list[tuple[str, int, str]], bindkey: str | None = None) -> MockConfigEntry:
    return MockConfigEntry(
        domain=DOMAIN,
        title="Waga",
        unique_id=ADDRESS,
        data={CONF_ADDRESS: ADDRESS, CONF_NAME: "Waga", CONF_TOKEN: TOKEN_HEX, "bindkey": bindkey},
        subentries_data=[
            ConfigSubentryData(
                subentry_type="person",
                title=name,
                unique_id=None,
                data={CONF_PROFILE_ID: pid, CONF_SEX: sex, CONF_BIRTHDAY: "1990-01-01", CONF_HEIGHT: 175},
            )
            for name, pid, sex in persons
        ],
    )


async def test_person_subentry_flow(hass: HomeAssistant) -> None:
    entry = _entry([("Dave", 1, "male")])
    entry.add_to_hass(hass)
    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    result = await hass.config_entries.subentries.async_init((entry.entry_id, "person"), context={"source": SOURCE_USER})
    assert result["type"] is FlowResultType.FORM
    data = {CONF_NAME: "Asia", CONF_PROFILE_ID: 1, CONF_SEX: "female", CONF_BIRTHDAY: "1992-05-05", CONF_HEIGHT: 165}
    result = await hass.config_entries.subentries.async_configure(result["flow_id"], data)
    assert result["errors"] == {CONF_PROFILE_ID: "profile_in_use"}
    result = await hass.config_entries.subentries.async_configure(result["flow_id"], {**data, CONF_PROFILE_ID: 2})
    assert result["type"] is FlowResultType.CREATE_ENTRY
    await hass.async_block_till_done()
    assert len(entry.subentries) == 2

    # Picking a Home Assistant person fills in the name.
    hass.states.async_set("person.tim", "home", {"friendly_name": "Tim"})
    result = await hass.config_entries.subentries.async_init((entry.entry_id, "person"), context={"source": SOURCE_USER})
    base = {CONF_SEX: "male", CONF_BIRTHDAY: "1990-01-01", CONF_HEIGHT: 180, CONF_PROFILE_ID: 3}
    result = await hass.config_entries.subentries.async_configure(result["flow_id"], base)
    assert result["errors"] == {CONF_NAME: "name_required"}
    result = await hass.config_entries.subentries.async_configure(
        result["flow_id"], {**base, "person_entity": "person.tim", CONF_BIRTHDAY: "2999-01-01"}
    )
    assert result["errors"] == {CONF_BIRTHDAY: "invalid_birthday"}
    result = await hass.config_entries.subentries.async_configure(result["flow_id"], {**base, "person_entity": "person.tim"})
    assert result["type"] is FlowResultType.CREATE_ENTRY
    tim = next(s for s in entry.subentries.values() if s.title == "Tim")
    assert tim.data["person_entity"] == "person.tim"


async def test_measurement_routed_to_person(hass: HomeAssistant) -> None:
    entry = _entry([("Dave", 1, "male"), ("Asia", 2, "female")])
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    coordinator = entry.runtime_data

    events = []
    hass.bus.async_listen(EVENT_MEASUREMENT, events.append)

    async def run(final_csv: str, live: list[str], stored: str = "") -> None:
        scale = FakeScale(bytes.fromhex(TOKEN_HEX))
        scale.stored = stored

        async def fake_connect(*args, **kwargs):
            return scale

        scale.disconnect = AsyncMock()
        with (
            patch("custom_components.xiaomi_s400.coordinator.establish_connection", side_effect=fake_connect),
            patch("custom_components.xiaomi_s400.coordinator.close_stale_connections_by_address", AsyncMock()),
            patch("custom_components.xiaomi_s400.coordinator.AFTER_FINAL_GRACE", 0.05),
            patch("custom_components.xiaomi_s400.coordinator.STORED_READ_DELAY", 0.1),
        ):
            task = hass.async_create_task(coordinator._async_session(object()))
            for _ in range(200):
                await asyncio.sleep(0.01)
                if scale.state == "ready":
                    break
            for w in live:
                scale.send_csv(w)
            scale.send_csv(final_csv)
            await asyncio.wait_for(task, 5)
        await hass.async_block_till_done()

    await run(FINAL_ASIA, ["400,0", "612,1"])

    reg = er.async_get(hass)
    ids = {e.unique_id: e.entity_id for e in er.async_entries_for_config_entry(reg, entry.entry_id)}
    dave_sub = next(s for s in entry.subentries.values() if s.title == "Dave").subentry_id
    asia_sub = next(s for s in entry.subentries.values() if s.title == "Asia").subentry_id

    def state(uid: str) -> str:
        return hass.states.get(ids[uid]).state

    assert state(f"{ADDRESS}_{asia_sub}_weight") == "61.2"
    assert state(f"{ADDRESS}_{dave_sub}_weight") == "unknown"
    assert state(f"{ADDRESS}_live_weight") == "61.2"
    assert state(f"{ADDRESS}_profile_id") == "2"
    assert float(state(f"{ADDRESS}_{asia_sub}_fat_percent")) > 0
    assert state(f"{ADDRESS}_connected") == "off"
    assert state(f"{ADDRESS}_stable") == "off"
    assert events[-1].data["person"] == "Asia"

    await run(FINAL_DAVE, ["909,1"])
    assert state(f"{ADDRESS}_{dave_sub}_weight") == "90.9"
    assert state(f"{ADDRESS}_{asia_sub}_weight") == "61.2"
    assert state(f"{ADDRESS}_{dave_sub}_impedance") == "489.0"

    # The scale's stored record for the same weigh-in replaces the estimated composition.
    stored = (
        "7,1,1,1,909,0,1,1760607100,251,620,535,31,12,170,310,297,700,-10,-50,-40,11,1810,4,40,71,"
        "682,34,228,681,486,155,4890,4413"
    )
    await run(FINAL_DAVE, ["909,1"], stored)
    assert state(f"{ADDRESS}_{dave_sub}_fat_percent") == "25.1"
    assert state(f"{ADDRESS}_{dave_sub}_body_score") == "71"
    assert state(f"{ADDRESS}_{dave_sub}_fat_mass") == "22.8"
    assert events[-1].data["source"] == "scale" and events[-1].data["fat_percent"] == 25.1

    # A weigh-in Home Assistant missed is backfilled from the scale's memory.
    missed = stored.replace("1760607100", "1760700000").replace(",909,", ",880,", 1)
    await run(FINAL_ASIA, [], missed)
    assert state(f"{ADDRESS}_{dave_sub}_weight") == "88.0"
    assert any(e.data["stored"] and e.data["person"] == "Dave" and e.data["weight"] == 88.0 for e in events)

    assert await hass.config_entries.async_unload(entry.entry_id)


BINDKEY = bytes.fromhex("0102030405060708090a0b0c0d0e0f10")


def _hr_adv(profile: int, weight_x10: int, hr: int, imp_x10: int):
    import struct

    from homeassistant.components.bluetooth import BluetoothServiceInfoBleak

    from custom_components.xiaomi_s400.s400.mibeacon import encrypt_advertisement

    packed = weight_x10 | ((hr - 50) << 11) | (imp_x10 << 18)
    obj = struct.pack("<HB", 0x6E16, 9) + struct.pack("<BII", profile, packed, 0)
    data = encrypt_advertisement(obj, ADDRESS, BINDKEY)
    info = MagicMock(spec=BluetoothServiceInfoBleak)
    info.service_data = {"0000fe95-0000-1000-8000-00805f9b34fb": data}
    info.rssi = -60
    return info


def test_mibeacon_roundtrip() -> None:
    from custom_components.xiaomi_s400.s400.mibeacon import decode_advertisement

    info = _hr_adv(2, 612, 66, 5650)
    r = decode_advertisement(info.service_data["0000fe95-0000-1000-8000-00805f9b34fb"], ADDRESS, BINDKEY)
    assert (r.profile_id, r.weight_kg, r.heart_rate, r.impedance_ohm) == (2, 61.2, 66, 565.0)
    assert decode_advertisement(info.service_data["0000fe95-0000-1000-8000-00805f9b34fb"], ADDRESS, bytes(16)) is None


async def test_heart_rate_from_advertisement(hass: HomeAssistant) -> None:
    entry = _entry([("Dave", 1, "male"), ("Asia", 2, "female")], bindkey=BINDKEY.hex())
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    coordinator = entry.runtime_data
    coordinator._last_session_end = 10**12  # suppress connection attempts from adverts

    events = []
    hass.bus.async_listen(EVENT_MEASUREMENT, events.append)

    from custom_components.xiaomi_s400.s400 import parse_payload

    from .fake_scale import csv_plaintext

    coordinator._handle_final(parse_payload(csv_plaintext(FINAL_ASIA)))
    await hass.async_block_till_done()
    assert events == []  # waits for heart rate

    coordinator._async_on_advertisement(_hr_adv(1, 909, 80, 4890), None)  # other person: ignored
    coordinator._async_on_advertisement(_hr_adv(2, 612, 66, 5650), None)
    await hass.async_block_till_done()

    reg = er.async_get(hass)
    ids = {e.unique_id: e.entity_id for e in er.async_entries_for_config_entry(reg, entry.entry_id)}
    asia_sub = next(s for s in entry.subentries.values() if s.title == "Asia").subentry_id
    assert hass.states.get(ids[f"{ADDRESS}_{asia_sub}_heart_rate"]).state == "66"
    assert hass.states.get(ids[f"{ADDRESS}_heart_rate"]).state == "66"
    assert len(events) == 1 and events[0].data["heart_rate"] == 66 and events[0].data["person"] == "Asia"
    assert await hass.config_entries.async_unload(entry.entry_id)


async def test_stays_connected_until_weigh_in(hass: HomeAssistant) -> None:
    """Regression for v0.2.x: the session must not drop after an idle period before anyone steps on."""
    entry = _entry([("Dave", 1, "male")])
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    coordinator = entry.runtime_data
    scale = FakeScale(bytes.fromhex(TOKEN_HEX))
    scale.disconnect = AsyncMock()

    async def fake_connect(*args, **kwargs):
        return scale

    with (
        patch("custom_components.xiaomi_s400.coordinator.establish_connection", side_effect=fake_connect),
        patch("custom_components.xiaomi_s400.coordinator.close_stale_connections_by_address", AsyncMock()),
        patch("custom_components.xiaomi_s400.coordinator.IDLE_CHECK", 0.02),
        patch("custom_components.xiaomi_s400.coordinator.AFTER_FINAL_GRACE", 0.05),
        patch("custom_components.xiaomi_s400.coordinator.STORED_READ_DELAY", 0.1),
    ):
        task = hass.async_create_task(coordinator._async_session(object()))
        for _ in range(300):
            await asyncio.sleep(0.01)
            if scale.state == "ready":
                break
        await asyncio.sleep(0.3)  # many idle periods after login
        assert not task.done()
        assert coordinator.state.connected
        scale.send_csv("909,1")
        scale.send_csv(FINAL_DAVE)
        await asyncio.wait_for(task, 5)
    assert coordinator.state.last_measurement.weight_kg == 90.9
    assert not coordinator.state.connected
    import time as _t

    assert coordinator._next_attempt - _t.monotonic() > 10  # pause after a measurement
    assert await hass.config_entries.async_unload(entry.entry_id)


async def test_reconnects_fast_after_scale_drops_link(hass: HomeAssistant) -> None:
    entry = _entry([("Dave", 1, "male")])
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    coordinator = entry.runtime_data
    scale = FakeScale(bytes.fromhex(TOKEN_HEX))
    scale.disconnect = AsyncMock()

    async def fake_connect(*args, disconnected_callback=None, **kwargs):
        hass.loop.call_later(0.1, disconnected_callback, scale)
        return scale

    with (
        patch("custom_components.xiaomi_s400.coordinator.establish_connection", side_effect=fake_connect),
        patch("custom_components.xiaomi_s400.coordinator.close_stale_connections_by_address", AsyncMock()),
    ):
        await asyncio.wait_for(coordinator._async_session(object()), 5)
    import time as _t

    assert coordinator._next_attempt - _t.monotonic() < 3
    assert await hass.config_entries.async_unload(entry.entry_id)


def test_heart_rate_matched_by_weight() -> None:
    from datetime import UTC, datetime

    from custom_components.xiaomi_s400.coordinator import Measurement, _same_weighing
    from custom_components.xiaomi_s400.s400.mibeacon import AdvReading

    m = Measurement(profile_id=1, weight_kg=76.0, impedance_ohm=493.0, impedance_low_ohm=445.0,
                    measured_at=datetime.now(UTC))
    # Real log: broadcast said profile 2 while the GATT frame said profile 1 for the same weigh-in.
    assert _same_weighing(AdvReading(2, 76.0, 80, 501.7, 59), m)
    assert not _same_weighing(AdvReading(2, 61.2, 70, 565.0, 60), m)
