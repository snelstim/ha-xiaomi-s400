"""Generate translations/en.json, translations/pl.json and strings.json.

Run: python scripts/gen_translations.py
"""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1] / "custom_components" / "xiaomi_s400"

BODY_TYPES = {
    "en": {
        "obese": "Obese", "overweight": "Overweight", "thick-set": "Thick-set",
        "lack-exercise": "Lack of exercise", "balanced": "Balanced",
        "balanced-muscular": "Balanced muscular", "skinny": "Skinny",
        "balanced-skinny": "Balanced skinny", "skinny-muscular": "Skinny muscular",
    },
    "pl": {
        "obese": "Otyłość", "overweight": "Nadwaga", "thick-set": "Krępa",
        "lack-exercise": "Brak ruchu", "balanced": "Zrównoważona",
        "balanced-muscular": "Zrównoważona umięśniona", "skinny": "Szczupła",
        "balanced-skinny": "Zrównoważona szczupła", "skinny-muscular": "Szczupła umięśniona",
    },
}

T = {
    "en": {
        "flow_title": "{name}",
        "user_title": "Xiaomi S400 scale",
        "user_desc": "Pick a discovered scale or enter its Bluetooth MAC address. The scale must be in range of a Home Assistant Bluetooth adapter or an ESPHome Bluetooth proxy with `active: true`.",
        "address": "MAC address",
        "cred_title": "Login token",
        "cred_desc": "Scale {address}. Paste the 24 hex character **TOKEN** shown for this scale by Xiaomi-cloud-tokens-extractor (not the 32 character BLE KEY).",
        "token": "Token",
        "name": "Name",
        "token_desc": "24 hex characters, e.g. 0123456789abcdef01234567",
        "bindkey": "BLE key (optional)",
        "bindkey_desc": "32 hex characters (BLE KEY from the extractor). Optional, only needed for heart rate, which the scale sends in its broadcast instead of the GATT stream.",
        "invalid_bindkey": "BLE key must be exactly 32 hex characters",
        "reauth_title": "Token rejected",
        "reauth_desc": "The scale rejected the login token. This happens after the scale was reset or re-added in Mi Home. Extract the token again and paste it here.",
        "reconf_title": "Change keys",
        "method_title": "Token and BLE key",
        "method_desc": "The scale's keys are stored in your Xiaomi account. Log in once to fetch them, or paste them from Xiaomi-cloud-tokens-extractor.",
        "menu_cloud": "Log in with Xiaomi Home (QR code)",
        "menu_manual": "Enter keys manually",
        "scan_qr": "Open **Xiaomi Home** on your phone, tap the scan icon and scan this code, then approve the login. Use the account the scale is added to.\n\n![QR code]({qr})\n\nCode not showing? [Open the login page]({url}). The keys are only read, nothing is changed in your account.",
        "cloud_failed": "Xiaomi login failed or timed out. Try again, or enter the keys manually.",
        "cloud_not_found": "Logged in, but this scale isn't in that Xiaomi account. Check you used the account the scale was added to.",
        "invalid_mac": "Invalid MAC address (expected AA:BB:CC:DD:EE:FF)",
        "invalid_token": "Token must be exactly 24 hex characters",
        "already_configured": "This scale is already configured",
        "not_supported": "This device is not a Xiaomi S400",
        "reauth_successful": "Token updated",
        "reconfigure_successful": "Token updated",
        "person_type": "Person",
        "person_add": "Add person",
        "person_reconf": "Edit person",
        "person_title": "Person",
        "person_desc": "Map a scale user profile to a person. Pick someone from Home Assistant's people (their name is used unless you type another), or just type a name. Weigh in alone once and check the **Profile ID** sensor to find which number is yours.",
        "person_entity": "Home Assistant person",
        "name_required": "Pick a person or enter a name",
        "invalid_birthday": "Enter a valid date of birth",
        "options_title": "Mode",
        "options_desc": "The scale only stores its own evaluation (body composition, body score) and broadcasts heart rate when no one is connected during the weigh-in, so pick one:",
        "mode": "Mode",
        "mode_live": "Live: stay connected for live weight; body composition is estimated by formula, no body score or heart rate",
        "mode_after": "After weigh-in: connect about 12 s after each weigh-in; the scale's own body composition, body score and heart rate (no live weight). Keep the Xiaomi app from syncing first",
        "profile_id": "Scale profile ID",
        "sex": "Sex",
        "birthday": "Date of birth",
        "height": "Height",
        "profile_in_use": "Another person already uses this profile ID",
        "male": "Male",
        "female": "Female",
        "e": {
            "on_scale": "On scale", "stable": "Stable", "connected": "Connected",
            "live_weight": "Live weight", "weight": "Weight", "impedance": "Impedance",
            "impedance_low": "Impedance low", "profile_id": "Profile ID", "heart_rate": "Heart rate",
            "last_measurement": "Last measurement", "last_error": "Last error",
            "raw_final": "Raw final frame", "bmi": "BMI", "fat_percent": "Body fat",
            "water_percent": "Water", "protein_percent": "Protein", "muscle_mass": "Muscle mass",
            "bone_mass": "Bone mass", "visceral_fat": "Visceral fat", "bmr": "Basal metabolism",
            "metabolic_age": "Metabolic age", "ideal_weight": "Ideal weight", "body_type": "Body type",
            "body_score": "Body score", "fat_mass": "Fat mass",
        },
    },
    "pl": {
        "flow_title": "{name}",
        "user_title": "Waga Xiaomi S400",
        "user_desc": "Wybierz wykrytą wagę lub wpisz jej adres MAC. Waga musi być w zasięgu adaptera Bluetooth Home Assistanta albo proxy Bluetooth ESPHome z `active: true`.",
        "address": "Adres MAC",
        "cred_title": "Token logowania",
        "cred_desc": "Waga {address}. Wklej 24-znakowy **TOKEN** tej wagi z Xiaomi-cloud-tokens-extractor (nie 32-znakowy BLE KEY).",
        "token": "Token",
        "name": "Nazwa",
        "token_desc": "24 znaki hex, np. 0123456789abcdef01234567",
        "bindkey": "BLE KEY (opcjonalnie)",
        "bindkey_desc": "32 znaki hex (BLE KEY z extractora). Opcjonalny, potrzebny tylko do tętna, które waga wysyła w rozgłoszeniu, a nie przez połączenie GATT.",
        "invalid_bindkey": "BLE KEY musi mieć dokładnie 32 znaki hex",
        "reauth_title": "Token odrzucony",
        "reauth_desc": "Waga odrzuciła token. Dzieje się tak po resecie wagi albo ponownym dodaniu jej w Mi Home. Wyciągnij token jeszcze raz i wklej go tutaj.",
        "reconf_title": "Zmień klucze",
        "method_title": "Token i BLE KEY",
        "method_desc": "Klucze wagi są zapisane na koncie Xiaomi. Zaloguj się raz, żeby je pobrać, albo wklej je z Xiaomi-cloud-tokens-extractor.",
        "menu_cloud": "Zaloguj przez Xiaomi Home (kod QR)",
        "menu_manual": "Wpisz klucze ręcznie",
        "scan_qr": "Otwórz **Xiaomi Home** na telefonie, stuknij ikonę skanowania, zeskanuj kod i zatwierdź logowanie. Użyj konta, do którego dodana jest waga.\n\n![Kod QR]({qr})\n\nKod się nie wyświetla? [Otwórz stronę logowania]({url}). Klucze są tylko odczytywane, nic nie jest zmieniane na koncie.",
        "cloud_failed": "Logowanie do Xiaomi nie powiodło się lub wygasło. Spróbuj ponownie albo wpisz klucze ręcznie.",
        "cloud_not_found": "Zalogowano, ale tej wagi nie ma na tym koncie Xiaomi. Sprawdź, czy to konto, do którego dodano wagę.",
        "invalid_mac": "Nieprawidłowy adres MAC (oczekiwany AA:BB:CC:DD:EE:FF)",
        "invalid_token": "Token musi mieć dokładnie 24 znaki hex",
        "already_configured": "Ta waga jest już skonfigurowana",
        "not_supported": "To urządzenie nie jest wagą Xiaomi S400",
        "reauth_successful": "Token zaktualizowany",
        "reconfigure_successful": "Token zaktualizowany",
        "person_type": "Osoba",
        "person_add": "Dodaj osobę",
        "person_reconf": "Edytuj osobę",
        "person_title": "Osoba",
        "person_desc": "Przypisz profil użytkownika wagi do osoby. Wybierz kogoś z osób Home Assistanta (użyta zostanie jego nazwa, chyba że wpiszesz inną) albo po prostu wpisz imię. Zważ się raz samodzielnie i sprawdź sensor **ID profilu**, żeby poznać swój numer.",
        "person_entity": "Osoba w Home Assistant",
        "name_required": "Wybierz osobę albo wpisz imię",
        "invalid_birthday": "Wpisz prawidłową datę urodzenia",
        "options_title": "Tryb",
        "options_desc": "Waga zapisuje własną ocenę (skład ciała, wynik) i rozgłasza tętno tylko wtedy, gdy podczas ważenia nikt nie jest połączony, więc wybierz:",
        "mode": "Tryb",
        "mode_live": "Na żywo: stałe połączenie i waga na żywo; skład ciała szacowany wzorem, bez wyniku ciała i tętna",
        "mode_after": "Po ważeniu: połączenie ok. 12 s po każdym ważeniu; własny skład ciała wagi, wynik ciała i tętno (bez wagi na żywo). Nie pozwól aplikacji Xiaomi zsynchronizować pierwszej",
        "profile_id": "ID profilu na wadze",
        "sex": "Płeć",
        "birthday": "Data urodzenia",
        "height": "Wzrost",
        "profile_in_use": "Inna osoba używa już tego ID profilu",
        "male": "Mężczyzna",
        "female": "Kobieta",
        "e": {
            "on_scale": "Na wadze", "stable": "Stabilny pomiar", "connected": "Połączona",
            "live_weight": "Waga na żywo", "weight": "Waga", "impedance": "Impedancja",
            "impedance_low": "Impedancja niska", "profile_id": "ID profilu", "heart_rate": "Tętno",
            "last_measurement": "Ostatni pomiar", "last_error": "Ostatni błąd",
            "raw_final": "Surowa ramka końcowa", "bmi": "BMI", "fat_percent": "Tłuszcz",
            "water_percent": "Woda", "protein_percent": "Białko", "muscle_mass": "Masa mięśni",
            "bone_mass": "Masa kości", "visceral_fat": "Tłuszcz trzewny", "bmr": "Podstawowa przemiana materii",
            "metabolic_age": "Wiek metaboliczny", "ideal_weight": "Waga idealna", "body_type": "Typ sylwetki",
            "body_score": "Wynik ciała", "fat_mass": "Masa tłuszczu",
        },
    },
}

BINARY = {"on_scale", "stable", "connected"}


def build(lang: str) -> dict:
    t = T[lang]
    token_schema = {"data": {"token": t["token"]}, "data_description": {"token": t["token_desc"]}}
    keys_schema = {
        "data": {"token": t["token"], "bindkey": t["bindkey"]},
        "data_description": {"token": t["token_desc"], "bindkey": t["bindkey_desc"]},
    }
    person_step = {
        "title": t["person_title"],
        "description": t["person_desc"],
        "data": {
            "person_entity": t["person_entity"], "name": t["name"], "profile_id": t["profile_id"], "sex": t["sex"],
            "birthday": t["birthday"], "height": t["height"],
        },
    }
    entity: dict = {"binary_sensor": {}, "sensor": {}}
    for key, name in t["e"].items():
        platform = "binary_sensor" if key in BINARY else "sensor"
        entity[platform][key] = {"name": name}
    entity["sensor"]["body_type"]["state"] = BODY_TYPES[lang]
    return {
        "config": {
            "flow_title": t["flow_title"],
            "step": {
                "user": {"title": t["user_title"], "description": t["user_desc"], "data": {"address": t["address"]}},
                "credentials": {
                    "title": t["cred_title"], "description": t["cred_desc"],
                    "data": {"token": t["token"], "bindkey": t["bindkey"], "name": t["name"]},
                    "data_description": {"token": t["token_desc"], "bindkey": t["bindkey_desc"]},
                },
                "reauth_confirm": {"title": t["reauth_title"], "description": t["reauth_desc"], **token_schema},
                "method": {
                    "title": t["method_title"], "description": t["method_desc"],
                    "menu_options": {"cloud": t["menu_cloud"], "credentials": t["menu_manual"]},
                },
                "reauth": {
                    "title": t["reauth_title"], "description": t["reauth_desc"],
                    "menu_options": {"cloud": t["menu_cloud"], "reauth_confirm": t["menu_manual"]},
                },
                "reconfigure": {
                    "title": t["reconf_title"],
                    "menu_options": {"cloud": t["menu_cloud"], "reconfigure_keys": t["menu_manual"]},
                },
                "reconfigure_keys": {"title": t["reconf_title"], **keys_schema},
                "cloud": {"title": t["menu_cloud"]},
            },
            "progress": {"scan_qr": t["scan_qr"]},
            "error": {
                "invalid_mac": t["invalid_mac"],
                "invalid_token": t["invalid_token"],
                "invalid_bindkey": t["invalid_bindkey"],
                "cloud_failed": t["cloud_failed"],
                "cloud_not_found": t["cloud_not_found"],
            },
            "abort": {
                "already_configured": t["already_configured"],
                "not_supported": t["not_supported"],
                "reauth_successful": t["reauth_successful"],
                "reconfigure_successful": t["reconfigure_successful"],
            },
        },
        "config_subentries": {
            "person": {
                "entry_type": t["person_type"],
                "initiate_flow": {"user": t["person_add"], "reconfigure": t["person_reconf"]},
                "step": {"user": person_step, "reconfigure": person_step},
                "error": {"profile_in_use": t["profile_in_use"], "name_required": t["name_required"],
                          "invalid_birthday": t["invalid_birthday"]},
                "abort": {"reconfigure_successful": t["reconfigure_successful"]},
            }
        },
        "options": {
            "step": {
                "init": {"title": t["options_title"], "description": t["options_desc"], "data": {"mode": t["mode"]}}
            }
        },
        "selector": {
            "sex": {"options": {"male": t["male"], "female": t["female"]}},
            "mode": {"options": {"live": t["mode_live"], "after": t["mode_after"]}},
        },
        "entity": entity,
    }


def main() -> None:
    (ROOT / "translations").mkdir(exist_ok=True)
    for lang in T:
        data = json.dumps(build(lang), ensure_ascii=False, indent=2) + "\n"
        (ROOT / "translations" / f"{lang}.json").write_text(data, encoding="utf-8")
        if lang == "en":
            (ROOT / "strings.json").write_text(data, encoding="utf-8")


if __name__ == "__main__":
    main()
