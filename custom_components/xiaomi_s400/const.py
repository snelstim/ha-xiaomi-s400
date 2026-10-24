"""Constants for Xiaomi S400."""

from __future__ import annotations

from datetime import timedelta

DOMAIN = "xiaomi_s400"

CONF_TOKEN = "token"
CONF_BINDKEY = "bindkey"
CONF_PROFILE_ID = "profile_id"
CONF_SEX = "sex"
CONF_BIRTHDAY = "birthday"
CONF_HEIGHT = "height"
CONF_PERSON_ENTITY = "person_entity"
CONF_MODE = "mode"
MODE_LIVE = "live"  # stay connected: live weight, formula body composition
MODE_AFTER = "after"  # connect after each weigh-in: the scale's own body composition and heart rate

SUBENTRY_PERSON = "person"

# MiBeacon product ids (bytes 2-3 of FE95 service data, little endian) of S400 variants.
S400_PRODUCT_IDS = {0x30D9, 0x3BD5, 0x48CF, 0x4B05}
MIBEACON_UUID = "0000fe95-0000-1000-8000-00805f9b34fb"

# While connected and idle, wake up this often to check the link (the connection is kept open).
IDLE_CHECK = 60.0
# Keep the link a little after the final frame in case more data follows.
AFTER_FINAL_GRACE = 4.0
# Read the weigh-ins stored on the scale (with its own body composition) this long after the final frame.
STORED_READ_DELAY = 8.0
# Accept a stored record as the GATT measurement it belongs to within this many seconds.
STORED_MATCH_WINDOW = 180
# After-weigh-in mode: connect this long after the broadcast counter last changed (the scale is
# done measuring and has stored the record by then).
AFTER_READ_DELAY = 12.0
# After-weigh-in mode: check what every Bluetooth radio last heard this often. HA forwards a device's
# broadcasts from one radio only (switching needs a 16 dB better signal), so the short weigh-in
# frames a closer proxy hears would otherwise be dropped.
SCANNER_POLL_INTERVAL = timedelta(seconds=1)
# After-weigh-in mode: use a broadcast heart rate seen this long before the stored record was read.
HEART_RATE_MATCH_WINDOW = 120.0
# After a measurement, stay disconnected so the scale can broadcast heart rate and the 2nd impedance.
POST_MEASUREMENT_PAUSE = 15.0
# Reconnect quickly when the scale drops an idle link.
RECONNECT_AFTER_DROP = 2.0
# Connection/login failures back off exponentially between these bounds.
FAILURE_BACKOFF_MIN = 5.0
FAILURE_BACKOFF_MAX = 120.0
# Also try to (re)connect on this interval, not only when the advertisement changes.
CONNECT_CHECK_INTERVAL = timedelta(seconds=5)

EVENT_MEASUREMENT = f"{DOMAIN}_measurement"

# Heart rate only comes in the advertisement after the measurement; wait this long for it.
HEART_RATE_WAIT = 20.0
# An unidentified weigh-in goes to the one person whose last weight is within this many kg.
WEIGHT_MATCH_KG = 3.0
