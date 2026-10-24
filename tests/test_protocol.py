"""Protocol-level tests: login handshake, CMTP reassembly, parsing, body composition."""

from __future__ import annotations

import asyncio

import pytest

from custom_components.xiaomi_s400.config_flow import normalize_token
from custom_components.xiaomi_s400.coordinator import age_from_birthday
from custom_components.xiaomi_s400.s400 import (
    BadTokenError,
    S400Session,
    UserProfile,
    compute,
    parse_payload,
)

from custom_components.xiaomi_s400.s400.miot import TYPE_STRING, TYPE_UINT8, build_action, parse_message
from custom_components.xiaomi_s400.s400.offline import build_request, parse_records

from .fake_scale import FakeScale, csv_plaintext

TOKEN = bytes.fromhex("00112233445566778899aabb")
FINAL_CSV = "0,0,2,905,1,2,1760607000," + ",".join(["0"] * 23) + ",4890,4413"


def test_parse_live() -> None:
    ev = parse_payload(csv_plaintext("907,0"))
    assert ev.type == "live"
    assert ev.weight_kg == pytest.approx(90.7)
    assert ev.stable is False


def test_parse_final() -> None:
    ev = parse_payload(csv_plaintext(FINAL_CSV))
    assert ev.type == "final"
    assert ev.profile_id == 2
    assert ev.weight_kg == pytest.approx(90.5)
    assert ev.timestamp == 1760607000
    assert ev.impedance_ohm == pytest.approx(489.0)
    assert ev.impedance_low_ohm == pytest.approx(441.3)
    assert len(ev.fields) == 32


def test_parse_unknown() -> None:
    assert parse_payload(b"\x01\x02\x03").type == "raw"


def test_body_composition() -> None:
    body = compute(90.5, 489.0, UserProfile(sex="male", age_years=35, height_cm=180))
    assert body["bmi"] == pytest.approx(27.9, abs=0.05)
    assert 5 < body["fat_percent"] < 45
    assert body["body_type_name"]


def test_age() -> None:
    from datetime import date

    assert age_from_birthday("1990-10-17", date(2026, 10, 16)) == 35
    assert age_from_birthday("1990-10-16", date(2026, 10, 16)) == 36


def test_normalize_token() -> None:
    assert normalize_token(" 00 11 22 33 44 55 66 77 88 99 AA BB ") == "00112233445566778899aabb"
    with pytest.raises(ValueError):
        normalize_token("abc")


async def test_login_and_stream() -> None:
    scale = FakeScale(TOKEN)
    session = S400Session(scale, TOKEN)
    await session.login()
    assert scale.login_ok

    scale.send_csv("812,0")
    scale.send_csv("905,1")
    scale.send_csv(FINAL_CSV)
    events = [await session.next_event(2) for _ in range(3)]
    assert [e.type for e in events] == ["live", "live", "final"]
    assert events[1].stable
    assert events[2].profile_id == 2
    assert await session.next_event(0.1) is None


async def test_login_bad_token() -> None:
    scale = FakeScale(TOKEN)
    session = S400Session(scale, bytes(12))
    with pytest.raises(BadTokenError):
        await session.login()


async def test_disconnect_ends_stream() -> None:
    scale = FakeScale(TOKEN)
    session = S400Session(scale, TOKEN)
    await session.login()
    asyncio.get_running_loop().call_later(0.05, session.mark_disconnected)
    assert await session.next_event(5) is None


# Illustrative record from the forum post (not real data).
RECORD = (
    "42,123456789,1,1,750,0,1,1790000000,200,565,580,32,7,170,310,231,700,-10,-50,-40,11,1666,4,38,82,"
    "753,43,150,600,435,128,5200,4750"
)


def miot_event(siid: int, eiid: int, piid: int, type_: int, value) -> bytes:
    msg = bytearray(build_action(7, siid, eiid, [(piid, type_, value)]))
    msg[4] = 0x07  # same layout as an action, different op
    return bytes(msg)


def test_offline_request_bytes() -> None:
    assert build_request(1) == bytes.fromhex("0e2001000509010001040001100" + "0")


def test_parse_miot_event() -> None:
    msg = parse_message(miot_event(9, 2, 3, TYPE_UINT8, 4))
    assert (msg.op, msg.siid, msg.iid, msg.values) == (7, 9, 2, {3: 4})


def test_parse_records() -> None:
    socks = RECORD.rsplit(",", 2)[0] + ",0,0"
    records = parse_records(RECORD + "_" + socks)
    assert len(records) == 2
    r = records[0]
    assert (r.user, r.weight_kg, r.timestamp) == (1, 75.0, 1790000000)
    assert (r.impedance_ohm, r.impedance_low_ohm) == (520.0, 475.0)
    assert r.body["fat_percent"] == 20.0
    assert r.body["fat_mass_kg"] == 15.0
    assert r.body["bmr_kcal_day"] == 1666
    assert r.body["body_score"] == 82
    assert r.body["body_type_name"] == "obese"  # 4, confirmed against Xiaomi Home
    assert r.heart_rate is None  # field 5 is 0 in this record
    assert records[1].impedance_ohm is None
    assert "fat_percent" not in records[1].body


async def test_request_offline_data() -> None:
    scale = FakeScale(TOKEN)
    session = S400Session(scale, TOKEN)
    await session.login()

    def respond(msg: bytes) -> None:
        assert msg == build_request(1)
        scale.send_plaintext(bytes.fromhex("0520010006") + b"\x00\x00")
        scale.send_plaintext(miot_event(9, 2, 3, TYPE_UINT8, 2))
        scale.send_csv("700,0")  # live frame interleaved: must not be lost
        scale.send_plaintext(miot_event(9, 1, 1, TYPE_STRING, RECORD + "_" + RECORD.replace("1790000000", "1790000100")))

    scale.on_message = respond
    records = await session.request_offline_data(timeout=3)
    assert [r.timestamp for r in records] == [1790000000, 1790000100]
    # No end-of-reception (siid 9 aiid 2) was sent, so the scale keeps the records.
    assert len(scale.app_in) == 1
    assert (await session.next_event(1)).type == "live"


def test_parse_real_record() -> None:
    """A real S400 record (fw 2.1.1_0006, account id replaced), checked against Xiaomi Home and the broadcast."""
    rec = parse_records(
        "9,123456789,1,1,1027,85,0,1792800837,308,673,471,38,18,177,349,317,700,-116,-327,-211,9,1906,4,38,75,"
        "655,37,316,711,483,182,4895,4447"
    )[0]
    assert (rec.user, rec.weight_kg, rec.heart_rate) == (1, 102.7, 85)
    assert (rec.impedance_ohm, rec.impedance_low_ohm) == (489.5, 444.7)
    b = rec.body
    assert (b["fat_percent"], b["fat_mass_kg"], b["muscle_mass_kg"], b["body_score"]) == (30.8, 31.6, 67.3, 75)
    assert (b["bmi"], b["bmr_kcal_day"], b["metabolic_age_years"], b["visceral_fat"]) == (31.7, 1906, 38, 18)
    assert b["body_type_name"] == "obese"
