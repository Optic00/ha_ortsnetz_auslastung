"""Tests for the status sensors after successful and failed transmissions."""

from datetime import timedelta
from unittest.mock import patch

import aiohttp
import pytest
from homeassistant.const import STATE_UNAVAILABLE
from homeassistant.util import dt as dt_util
from pytest_homeassistant_custom_component.common import MockConfigEntry, async_fire_time_changed
from pytest_homeassistant_custom_component.test_util.aiohttp import AiohttpClientMockResponse

from custom_components.ortsnetz_auslastung.const import DOMAIN

URL = "https://example.test/v1/measurements"
STATUS = "sensor.netzspannungsstatus"
RECOMMENDATION = "sensor.batteriespeicherempfehlung"
GOOD = {
    "status": {"l1": "green", "l2": "yellow", "l3": "green", "overall": "yellow"},
    "storage_recommendation": "charge",
}


@pytest.fixture(autouse=True)
def no_sleep():
    with patch("custom_components.ortsnetz_auslastung.asyncio.sleep"):
        yield


async def _setup(hass, aioclient_mock, **response):
    for entity_id, value in (("sensor.l1", "230"), ("sensor.l2", "231"), ("sensor.l3", "229")):
        hass.states.async_set(entity_id, value)
    aioclient_mock.post(URL, **response)
    entry = MockConfigEntry(domain=DOMAIN, version=3, data={
        "api_url": URL, "l1_entity": "sensor.l1", "l2_entity": "sensor.l2", "l3_entity": "sensor.l3",
        "latitude": 52.5, "longitude": 13.4,
    })
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry


async def _next_cycle(hass, aioclient_mock, **response):
    aioclient_mock.clear_requests()
    aioclient_mock.post(URL, **response)
    async_fire_time_changed(hass, dt_util.utcnow() + timedelta(minutes=5, seconds=1))
    await hass.async_block_till_done()


async def test_valid_response_sets_values(hass, aioclient_mock):
    await _setup(hass, aioclient_mock, json=GOOD)
    assert hass.states.get(STATUS).state == "Warnung"
    assert hass.states.get(STATUS).attributes["L2"] == "Warnung"
    assert hass.states.get(RECOMMENDATION).state == "Laden"


@pytest.mark.parametrize("response", [
    {"status": 500},
    {"status": 403},
    {"exc": aiohttp.ClientConnectionError()},
    {"exc": aiohttp.ServerDisconnectedError()},
    {"text": "<html>kein json</html>"},
    {"json": ["unerwartet"]},
    {"json": {"status": {"l1": [], "l2": "green", "l3": "green", "overall": "green"}, "storage_recommendation": {}}},
])
async def test_failure_marks_previous_values_unavailable(hass, aioclient_mock, response):
    await _setup(hass, aioclient_mock, json=GOOD)
    await _next_cycle(hass, aioclient_mock, **response)
    assert hass.states.get(STATUS).state == STATE_UNAVAILABLE
    assert hass.states.get(RECOMMENDATION).state == STATE_UNAVAILABLE


async def test_missing_voltage_sensor_marks_unavailable_without_post(hass, aioclient_mock):
    await _setup(hass, aioclient_mock, json=GOOD)
    hass.states.async_set("sensor.l2", "unavailable")
    await _next_cycle(hass, aioclient_mock, json=GOOD)
    assert aioclient_mock.call_count == 0
    assert hass.states.get(STATUS).state == STATE_UNAVAILABLE
    assert hass.states.get(RECOMMENDATION).state == STATE_UNAVAILABLE


async def test_values_return_after_recovery(hass, aioclient_mock):
    await _setup(hass, aioclient_mock, status=500)
    assert hass.states.get(STATUS).state == STATE_UNAVAILABLE
    await _next_cycle(hass, aioclient_mock, json=GOOD)
    assert hass.states.get(STATUS).state == "Warnung"
    assert hass.states.get(RECOMMENDATION).state == "Laden"


async def test_invalid_recommendation_only_affects_that_sensor(hass, aioclient_mock):
    await _setup(hass, aioclient_mock, json=GOOD)
    await _next_cycle(hass, aioclient_mock, json={**GOOD, "storage_recommendation": "bogus"})
    assert hass.states.get(STATUS).state == "Warnung"
    assert hass.states.get(RECOMMENDATION).state == STATE_UNAVAILABLE


async def test_http_error_retries_once(hass, aioclient_mock):
    await _setup(hass, aioclient_mock, json=GOOD)
    await _next_cycle(hass, aioclient_mock, status=500)
    assert aioclient_mock.call_count == 2


async def test_invalid_json_is_not_resent(hass, aioclient_mock):
    await _setup(hass, aioclient_mock, json=GOOD)
    await _next_cycle(hass, aioclient_mock, text="kein json")
    assert aioclient_mock.call_count == 1


async def test_implausible_voltage_skips_post(hass, aioclient_mock):
    await _setup(hass, aioclient_mock, json=GOOD)
    hass.states.async_set("sensor.l1", "23000")
    await _next_cycle(hass, aioclient_mock, json=GOOD)
    assert aioclient_mock.call_count == 0
    assert hass.states.get(STATUS).state == STATE_UNAVAILABLE


async def test_success_on_retry_keeps_values(hass, aioclient_mock):
    await _setup(hass, aioclient_mock, json=GOOD)
    responses = iter([aiohttp.ClientConnectionError(), None])

    async def side_effect(method, url, data):
        error = next(responses)
        if error:
            raise error
        return AiohttpClientMockResponse(method, url, json=GOOD)

    await _next_cycle(hass, aioclient_mock, side_effect=side_effect)
    assert aioclient_mock.call_count == 2
    assert hass.states.get(STATUS).state == "Warnung"
    assert hass.states.get(RECOMMENDATION).state == "Laden"


async def test_invalid_status_only_affects_that_sensor(hass, aioclient_mock):
    await _setup(hass, aioclient_mock, json=GOOD)
    await _next_cycle(hass, aioclient_mock, json={**GOOD, "status": {"overall": "green"}})
    assert hass.states.get(STATUS).state == STATE_UNAVAILABLE
    assert hass.states.get(RECOMMENDATION).state == "Laden"
