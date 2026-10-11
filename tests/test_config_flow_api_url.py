"""Tests for the HTTPS check of the API address in the config and options flow."""

import pytest
from homeassistant.data_entry_flow import FlowResultType
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.ortsnetz_auslastung.const import DOMAIN

PHASES = {"l1_entity": "sensor.l1", "l2_entity": "sensor.l2", "l3_entity": "sensor.l3"}
INVALID_URLS = [
    "http://www.ortsnetz-auslastung.de",
    "https://",
    "www.ortsnetz-auslastung.de",
    "https://www.ortsnetz-auslastung.de:abc",
    "https://www.ortsnetz auslastung.de",
]


def _form(api_url):
    return {"api_url": api_url, "phase_voltages": PHASES, "latitude": 52.5, "longitude": 13.4}


@pytest.mark.parametrize("api_url", [
    "https://www.ortsnetz-auslastung.de",
    "https://www.ortsnetz-auslastung.de/v1/measurements",
])
async def test_user_step_accepts_https(hass, api_url):
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": "user"})
    result = await hass.config_entries.flow.async_configure(result["flow_id"], _form(api_url))
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["data"]["api_url"] == api_url


async def test_user_step_strips_whitespace(hass):
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": "user"})
    result = await hass.config_entries.flow.async_configure(result["flow_id"], _form("  https://www.ortsnetz-auslastung.de "))
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["data"]["api_url"] == "https://www.ortsnetz-auslastung.de"


@pytest.mark.parametrize("api_url", INVALID_URLS)
async def test_user_step_rejects_invalid_url(hass, api_url):
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": "user"})
    result = await hass.config_entries.flow.async_configure(result["flow_id"], _form(api_url))
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"api_url": "invalid_api_url"}


async def _options_flow(hass):
    entry = MockConfigEntry(domain=DOMAIN, version=3, data={
        "api_url": "https://www.ortsnetz-auslastung.de", **PHASES, "latitude": 52.5, "longitude": 13.4,
    })
    entry.add_to_hass(hass)
    return entry, await hass.config_entries.options.async_init(entry.entry_id)


@pytest.mark.parametrize("api_url", INVALID_URLS)
async def test_options_rejects_invalid_url(hass, api_url):
    entry, result = await _options_flow(hass)
    result = await hass.config_entries.options.async_configure(result["flow_id"], _form(api_url))
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"api_url": "invalid_api_url"}
    assert entry.options == {}


async def test_options_accepts_https(hass):
    entry, result = await _options_flow(hass)
    result = await hass.config_entries.options.async_configure(result["flow_id"], _form("https://example.org/v1/measurements"))
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert entry.options["api_url"] == "https://example.org/v1/measurements"
