"""Config flow for Xiaomi S400."""

from __future__ import annotations

import asyncio
import logging
import re
from collections.abc import Mapping
from datetime import date
from typing import Any

import voluptuous as vol
from homeassistant.components.bluetooth import (
    BluetoothServiceInfoBleak,
    async_discovered_service_info,
)
from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    ConfigSubentryFlow,
    SubentryFlowResult,
)
from homeassistant.const import CONF_ADDRESS, CONF_NAME
from homeassistant.core import callback
from homeassistant.helpers import selector
from homeassistant.helpers.aiohttp_client import async_create_clientsession

from .cloud import SERVERS, CloudDevice, CloudError, XiaomiCloud

from .const import (
    CONF_BINDKEY,
    CONF_BIRTHDAY,
    CONF_HEIGHT,
    CONF_PERSON_ENTITY,
    CONF_PROFILE_ID,
    CONF_SEX,
    CONF_TOKEN,
    DOMAIN,
    MIBEACON_UUID,
    S400_PRODUCT_IDS,
    SUBENTRY_PERSON,
)

_LOGGER = logging.getLogger(__name__)

MAC_RE = re.compile(r"^([0-9A-F]{2}:){5}[0-9A-F]{2}$")


def normalize_token(value: str) -> str:
    """Return token as 24 lowercase hex chars or raise ValueError."""
    token = re.sub(r"[^0-9a-fA-F]", "", value).lower()
    if len(token) != 24:
        raise ValueError
    return token


def normalize_bindkey(value: str | None) -> str | None:
    """Return bindkey as 32 lowercase hex chars, None when empty, or raise ValueError."""
    if not value or not value.strip():
        return None
    key = re.sub(r"[^0-9a-fA-F]", "", value).lower()
    if len(key) != 32:
        raise ValueError
    return key


def _secret() -> selector.TextSelector:
    return selector.TextSelector(selector.TextSelectorConfig(type=selector.TextSelectorType.PASSWORD))


def is_s400(info: BluetoothServiceInfoBleak) -> bool:
    """Check the MiBeacon product id in FE95 service data."""
    data = info.service_data.get(MIBEACON_UUID)
    if not data or len(data) < 4:
        return False
    return int.from_bytes(data[2:4], "little") in S400_PRODUCT_IDS


class S400ConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow."""

    VERSION = 1

    def __init__(self) -> None:
        self._discovered: dict[str, str] = {}
        self._address: str | None = None
        self._cloud: XiaomiCloud | None = None
        self._cloud_task: asyncio.Task | None = None
        self._cloud_error: str | None = None
        self._prefill: dict[str, Any] = {}
        self._keys_step = "credentials"  # where the cloud login hands its keys over

    @classmethod
    @callback
    def async_get_supported_subentry_types(cls, config_entry: ConfigEntry) -> dict[str, type[ConfigSubentryFlow]]:
        return {SUBENTRY_PERSON: PersonSubentryFlow}

    async def async_step_bluetooth(self, discovery_info: BluetoothServiceInfoBleak) -> ConfigFlowResult:
        if not is_s400(discovery_info):
            return self.async_abort(reason="not_supported")
        await self.async_set_unique_id(discovery_info.address.upper())
        self._abort_if_unique_id_configured()
        self._address = discovery_info.address.upper()
        self.context["title_placeholders"] = {"name": discovery_info.name or self._address}
        return await self.async_step_method()

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            address = user_input[CONF_ADDRESS].strip().upper()
            if not MAC_RE.match(address):
                errors[CONF_ADDRESS] = "invalid_mac"
            else:
                await self.async_set_unique_id(address)
                self._abort_if_unique_id_configured()
                self._address = address
                return await self.async_step_method()

        current = self._async_current_ids(include_ignore=False)
        for info in async_discovered_service_info(self.hass, connectable=False):
            addr = info.address.upper()
            if addr not in current and is_s400(info):
                self._discovered[addr] = f"{info.name or 'S400'} ({addr})"

        if self._discovered:
            field = selector.SelectSelector(
                selector.SelectSelectorConfig(
                    options=[selector.SelectOptionDict(value=k, label=v) for k, v in self._discovered.items()],
                    custom_value=True,
                    mode=selector.SelectSelectorMode.DROPDOWN,
                )
            )
        else:
            field = str
        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema({vol.Required(CONF_ADDRESS): field}),
            errors=errors,
        )

    async def async_step_method(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        self._keys_step = "credentials"
        return self.async_show_menu(step_id="method", menu_options=["cloud", "credentials"])

    # ---- Xiaomi cloud QR login -------------------------------------------

    async def async_step_cloud(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        if self._cloud_task is None:
            self._cloud = XiaomiCloud(async_create_clientsession(self.hass))
            try:
                await self._cloud.start_qr_login()
            except (CloudError, OSError, ValueError) as err:
                _LOGGER.warning("Xiaomi cloud login failed: %s", err)
                self._cloud_error = "cloud_failed"
                return await self.async_step_cloud_result()
            self._cloud_task = self.hass.async_create_task(self._async_cloud_fetch())
        if not self._cloud_task.done():
            assert self._cloud is not None
            return self.async_show_progress(
                step_id="cloud",
                progress_action="scan_qr",
                progress_task=self._cloud_task,
                description_placeholders={"qr": self._cloud.qr_image_url, "url": self._cloud.login_url},
            )
        return self.async_show_progress_done(next_step_id="cloud_result")

    async def _async_cloud_fetch(self) -> None:
        assert self._cloud is not None and self._address is not None
        try:
            await self._cloud.wait_for_scan()
            devices: list[CloudDevice] = []
            match: CloudDevice | None = None
            for server in SERVERS:  # stop at the first region that has the scale
                devices += await self._cloud.find_devices([server])
                if match := next((d for d in devices if d.mac == self._address and d.token), None):
                    break
        except Exception as err:  # noqa: BLE001 - always end the progress step, never leave it spinning
            _LOGGER.warning("Xiaomi cloud login failed: %s", err, exc_info=not isinstance(err, CloudError))
            self._cloud_error = "cloud_failed"
            return
        if match is None:
            _LOGGER.warning(
                "Scale %s not in this Xiaomi account; found %s",
                self._address, [(d.model, d.mac) for d in devices],
            )
            self._cloud_error = "cloud_not_found"
            return
        self._prefill = {CONF_TOKEN: match.token, CONF_BINDKEY: match.bindkey, CONF_NAME: match.name}

    async def async_step_cloud_result(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Continue to the keys form, filled in from the cloud (or with an error to enter them by hand)."""
        self._cloud_task = None
        return await getattr(self, f"async_step_{self._keys_step}")()

    def _cloud_errors(self) -> dict[str, str]:
        errors = {"base": self._cloud_error} if self._cloud_error else {}
        self._cloud_error = None
        return errors

    async def async_step_credentials(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            token, bindkey = _validate_keys(user_input, errors)
            if not errors:
                name = user_input.get(CONF_NAME) or "Xiaomi S400"
                return self.async_create_entry(
                    title=name,
                    data={CONF_ADDRESS: self._address, CONF_NAME: name, CONF_TOKEN: token, CONF_BINDKEY: bindkey},
                )
        if user_input is None:
            errors = self._cloud_errors()
        return self.async_show_form(
            step_id="credentials",
            data_schema=self.add_suggested_values_to_schema(
                vol.Schema(
                    {
                        vol.Required(CONF_TOKEN): _secret(),
                        vol.Optional(CONF_BINDKEY): _secret(),
                        vol.Optional(CONF_NAME, default="Xiaomi S400"): str,
                    }
                ),
                user_input or self._prefill,
            ),
            description_placeholders={"address": self._address or ""},
            errors=errors,
        )

    async def async_step_reauth(self, entry_data: Mapping[str, Any]) -> ConfigFlowResult:
        self._address = self._get_reauth_entry().data[CONF_ADDRESS]
        self._keys_step = "reauth_confirm"
        return self.async_show_menu(step_id="reauth", menu_options=["cloud", "reauth_confirm"])

    async def async_step_reauth_confirm(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            try:
                token = normalize_token(user_input[CONF_TOKEN])
            except ValueError:
                errors[CONF_TOKEN] = "invalid_token"
            else:
                return self.async_update_and_abort(
                    self._get_reauth_entry(), data_updates={CONF_TOKEN: token}
                )
        if user_input is None:
            errors = self._cloud_errors()
        return self.async_show_form(
            step_id="reauth_confirm",
            data_schema=self.add_suggested_values_to_schema(
                vol.Schema({vol.Required(CONF_TOKEN): _secret()}), self._prefill
            ),
            errors=errors,
        )

    async def async_step_reconfigure(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        self._address = self._get_reconfigure_entry().data[CONF_ADDRESS]
        self._keys_step = "reconfigure_keys"
        return self.async_show_menu(step_id="reconfigure", menu_options=["cloud", "reconfigure_keys"])

    async def async_step_reconfigure_keys(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            token, bindkey = _validate_keys(user_input, errors)
            if not errors:
                return self.async_update_and_abort(
                    self._get_reconfigure_entry(), data_updates={CONF_TOKEN: token, CONF_BINDKEY: bindkey}
                )
        entry = self._get_reconfigure_entry()
        if user_input is None:
            errors = self._cloud_errors()
        return self.async_show_form(
            step_id="reconfigure_keys",
            data_schema=self.add_suggested_values_to_schema(
                vol.Schema({vol.Required(CONF_TOKEN): _secret(), vol.Optional(CONF_BINDKEY): _secret()}),
                self._prefill or {CONF_TOKEN: entry.data.get(CONF_TOKEN), CONF_BINDKEY: entry.data.get(CONF_BINDKEY)},
            ),
            errors=errors,
        )


def _validate_keys(user_input: dict[str, Any], errors: dict[str, str]) -> tuple[str | None, str | None]:
    token = bindkey = None
    try:
        token = normalize_token(user_input[CONF_TOKEN])
    except ValueError:
        errors[CONF_TOKEN] = "invalid_token"
    try:
        bindkey = normalize_bindkey(user_input.get(CONF_BINDKEY))
    except ValueError:
        errors[CONF_BINDKEY] = "invalid_bindkey"
    return token, bindkey


def _person_schema(defaults: Mapping[str, Any]) -> vol.Schema:
    return vol.Schema(
        {
            vol.Optional(
                CONF_PERSON_ENTITY, default=defaults.get(CONF_PERSON_ENTITY) or vol.UNDEFINED
            ): selector.EntitySelector(selector.EntitySelectorConfig(domain="person")),
            vol.Optional(CONF_NAME, default=defaults.get(CONF_NAME, vol.UNDEFINED)): str,
            vol.Required(CONF_PROFILE_ID, default=defaults.get(CONF_PROFILE_ID, 1)): selector.NumberSelector(
                selector.NumberSelectorConfig(min=1, max=16, step=1, mode=selector.NumberSelectorMode.BOX)
            ),
            vol.Required(CONF_SEX, default=defaults.get(CONF_SEX, "male")): selector.SelectSelector(
                selector.SelectSelectorConfig(options=["male", "female"], translation_key="sex")
            ),
            vol.Required(CONF_BIRTHDAY, default=defaults.get(CONF_BIRTHDAY, vol.UNDEFINED)): selector.TextSelector(
                # The browser's own date input: the year can be typed, unlike HA's month-by-month picker.
                selector.TextSelectorConfig(type=selector.TextSelectorType.DATE)
            ),
            vol.Required(CONF_HEIGHT, default=defaults.get(CONF_HEIGHT, 175)): selector.NumberSelector(
                selector.NumberSelectorConfig(
                    min=80, max=230, step=1, unit_of_measurement="cm", mode=selector.NumberSelectorMode.BOX
                )
            ),
        }
    )


class PersonSubentryFlow(ConfigSubentryFlow):
    """Add or edit a person mapped to a scale profile id."""

    def _validate(
        self, user_input: dict[str, Any], exclude: str | None
    ) -> tuple[str, dict[str, Any], dict[str, str]]:
        person_entity = user_input.get(CONF_PERSON_ENTITY) or None
        name = (user_input.get(CONF_NAME) or "").strip()
        if not name and person_entity and (state := self.hass.states.get(person_entity)):
            name = state.name
        data = {
            CONF_PERSON_ENTITY: person_entity,
            CONF_PROFILE_ID: int(user_input[CONF_PROFILE_ID]),
            CONF_SEX: user_input[CONF_SEX],
            CONF_BIRTHDAY: user_input[CONF_BIRTHDAY],
            CONF_HEIGHT: int(user_input[CONF_HEIGHT]),
        }
        errors: dict[str, str] = {}
        try:
            born = date.fromisoformat(str(data[CONF_BIRTHDAY]).strip())
        except ValueError:
            errors[CONF_BIRTHDAY] = "invalid_birthday"
        else:
            if not date(1900, 1, 1) <= born < date.today():
                errors[CONF_BIRTHDAY] = "invalid_birthday"
            data[CONF_BIRTHDAY] = born.isoformat()
        if not name:
            errors[CONF_NAME] = "name_required"
        for sub in self._get_entry().subentries.values():
            if sub.subentry_id != exclude and sub.data.get(CONF_PROFILE_ID) == data[CONF_PROFILE_ID]:
                errors[CONF_PROFILE_ID] = "profile_in_use"
        return name, data, errors

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> SubentryFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            name, data, errors = self._validate(user_input, None)
            if not errors:
                return self.async_create_entry(title=name, data=data)
        return self.async_show_form(step_id="user", data_schema=_person_schema(user_input or {}), errors=errors)

    async def async_step_reconfigure(self, user_input: dict[str, Any] | None = None) -> SubentryFlowResult:
        subentry = self._get_reconfigure_subentry()
        errors: dict[str, str] = {}
        if user_input is not None:
            name, data, errors = self._validate(user_input, subentry.subentry_id)
            if not errors:
                return self.async_update_and_abort(self._get_entry(), subentry, title=name, data=data)
        defaults = user_input or {CONF_NAME: subentry.title, **subentry.data}
        return self.async_show_form(step_id="reconfigure", data_schema=_person_schema(defaults), errors=errors)
