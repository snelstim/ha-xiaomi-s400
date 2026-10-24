"""Weigh-ins stored on the scale (MIoT service 9, offline-data), with the scale's own body composition.

The scale keeps every weigh-in (up to 160) until the Xiaomi app acknowledges it with
end-of-reception (siid 9, aiid 2). We never send that, so the app still gets them.

Records are separated by "_", each made of 33 comma-separated integers. Field map from
https://community.home-assistant.io/t/662778 (firmware 2.1.1_0006). Field 5 is the heart rate (confirmed against the broadcast). Unidentified: 3, 6, 14, 17, 19, 20.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .miot import TYPE_UINT8, build_action

SIID_OFFLINE = 9
AIID_REQUEST = 1  # request-offline-data
EIID_RECORDS = 1  # piid 1: records string
EIID_COUNT = 2  # piid 3: number of records
PIID_ONLY_UPLOAD_COUNT = 4

RECORD_FIELDS = 33

# The scale's body-type value -> name, from the Xiaomi Home plugin for this scale
# (yunmai.scales.ms104 v31, _getBodyTypeTitle). The chart's two "Overweight" cells are both 2.
SCALE_BODY_TYPES: dict[int, str] = {
    -5: "lean",
    -4: "underweight",
    -3: "invisibly-obese",
    -2: "slim-muscular",
    -1: "slim",
    0: "fit",
    1: "muscular",
    2: "overweight",
    3: "athletic",
    4: "obese",
}


def build_request(tid: int) -> bytes:
    return build_action(tid, SIID_OFFLINE, AIID_REQUEST, [(PIID_ONLY_UPLOAD_COUNT, TYPE_UINT8, 0)])


@dataclass
class StoredRecord:
    """One weigh-in as stored and evaluated by the scale."""

    index: int
    user: int
    weight_kg: float
    timestamp: int
    impedance_ohm: float | None
    impedance_low_ohm: float | None
    heart_rate: int | None = None
    body: dict[str, Any] = field(default_factory=dict)
    raw: list[int] = field(default_factory=list)


def _div10(v: int) -> float:
    return round(v / 10, 1)


def parse_record(text: str) -> StoredRecord | None:
    try:
        f = [int(x) for x in text.strip().split(",")]
    except ValueError:
        return None
    if len(f) < RECORD_FIELDS or f[4] <= 0:
        return None
    body: dict[str, Any] = {
        "fat_percent": _div10(f[8]),
        "muscle_mass_kg": _div10(f[9]),
        "water_percent": _div10(f[10]),
        "bone_mass_kg": _div10(f[11]),
        "visceral_fat": f[12],
        "protein_percent": _div10(f[13]),
        "bmi": _div10(f[15]),
        "ideal_weight_kg": _div10(f[16]),
        "bmr_kcal_day": f[21],
        "metabolic_age_years": f[23],
        "body_score": f[24],
        "muscle_percent": _div10(f[25]),
        "bone_percent": _div10(f[26]),
        "fat_mass_kg": _div10(f[27]),
        "fat_free_mass_kg": _div10(f[28]),
        "water_mass_kg": _div10(f[29]),
        "protein_mass_kg": _div10(f[30]),
    }
    # Without impedance (socks) the scale only knows weight and BMI; drop the zeroed composition.
    # The same when it didn't recognise anyone (user 0): it evaluates nothing.
    if not f[2]:
        body = {}
    elif not f[31] and not f[32]:
        body = {"bmi": body["bmi"]} if f[15] else {}
    elif f[22] in SCALE_BODY_TYPES:
        body["body_type"] = f[22]
        body["body_type_name"] = SCALE_BODY_TYPES[f[22]]
    body["source"] = "scale"
    return StoredRecord(
        index=f[0],
        user=f[2],
        weight_kg=_div10(f[4]),
        timestamp=f[7],
        impedance_ohm=_div10(f[31]) if f[31] else None,
        impedance_low_ohm=_div10(f[32]) if f[32] else None,
        heart_rate=f[5] if 30 <= f[5] <= 230 else None,
        body=body,
        raw=f,
    )


def parse_records(text: str) -> list[StoredRecord]:
    return [r for part in text.split("_") if part.strip() and (r := parse_record(part))]
