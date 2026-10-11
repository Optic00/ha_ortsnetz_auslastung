"""Tests for the transmitted version and the sensor polling setting."""

import json
from pathlib import Path

from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.ortsnetz_auslastung import _send
from custom_components.ortsnetz_auslastung.const import DOMAIN

URL = "https://example.test/v1/measurements"
MANIFEST = Path(__file__).parents[1] / "custom_components" / DOMAIN / "manifest.json"


def _entry(hass):
    entry = MockConfigEntry(domain=DOMAIN, version=3, data={
        "api_url": URL, "l1_entity": "sensor.l1", "l2_entity": "sensor.l2", "l3_entity": "sensor.l3",
        "latitude": 52.5, "longitude": 13.4,
    })
    entry.add_to_hass(hass)
    return entry


async def test_payload_contains_manifest_version(hass, aioclient_mock):
    for entity_id in ("sensor.l1", "sensor.l2", "sensor.l3"):
        hass.states.async_set(entity_id, "230")
    aioclient_mock.post(URL, json={})

    await _send(hass, _entry(hass))

    assert aioclient_mock.mock_calls[0][2]["integration_version"] == json.loads(MANIFEST.read_text())["version"]


async def test_sensors_are_not_polled(hass, aioclient_mock):
    aioclient_mock.post(URL, json={})
    entry = _entry(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    entities = [entity for entity in hass.data["sensor"].entities if entity.platform.config_entry is entry]
    assert len(entities) == 2
    assert not any(entity.should_poll for entity in entities)
