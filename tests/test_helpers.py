"""Tests for the Bravia Quad helpers module."""

from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import MagicMock, patch

import pytest
from homeassistant.const import CONF_HOST, CONF_MAC, Platform
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.device_registry import CONNECTION_NETWORK_MAC
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.bravia_quad.const import (
    CONF_HAS_SUBWOOFER,
    CONF_MODEL,
    DOMAIN,
)
from custom_components.bravia_quad.helpers import (
    get_device_info,
    migrate_legacy_identifiers,
    verify_feature_value,
)

if TYPE_CHECKING:
    from unittest.mock import MagicMock

    from homeassistant.core import HomeAssistant


# =============================================================================
# Device registry enrichment tests
# =============================================================================


@pytest.fixture
def platforms() -> list[Platform]:
    """Load no platforms for these tests."""
    return []


@pytest.mark.usefixtures("mock_bravia_quad_client")
async def test_device_registry_model_from_tcp(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_bravia_quad_client: MagicMock,
) -> None:
    """Test device registry gets model name resolved from TCP model type."""
    # Entry has no CONF_MODEL (manual setup, no zeroconf)
    mock_config_entry.add_to_hass(hass)

    with patch("custom_components.bravia_quad.PLATFORMS", []):
        await hass.config_entries.async_setup(mock_config_entry.entry_id)
        await hass.async_block_till_done()

    device_registry = dr.async_get(hass)
    device = device_registry.async_get_device(
        identifiers={(DOMAIN, mock_config_entry.unique_id)}
    )
    assert device is not None
    # model_type "HT-A9M2" should resolve to "BRAVIA Theatre Quad" via lookup
    assert device.model == "BRAVIA Theatre Quad"
    assert device.model_id == "HT-A9M2"
    assert device.manufacturer == "SONY"
    assert device.serial_number == "1234567"
    assert device.sw_version == "001.100"


@pytest.mark.usefixtures("mock_bravia_quad_client")
async def test_device_registry_model_from_zeroconf(
    hass: HomeAssistant,
    mock_bravia_quad_client: MagicMock,
) -> None:
    """Test device registry prefers zeroconf model name over TCP fallback."""
    entry = MockConfigEntry(
        title="Bravia Quad",
        domain=DOMAIN,
        data={
            CONF_HOST: "192.168.1.100",
            CONF_HAS_SUBWOOFER: True,
            CONF_MODEL: "BRAVIA Theatre Quad",
        },
        unique_id="192.168.1.100",
        entry_id="test_zeroconf_entry",
    )
    entry.add_to_hass(hass)

    with patch("custom_components.bravia_quad.PLATFORMS", []):
        await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

    device_registry = dr.async_get(hass)
    device = device_registry.async_get_device(identifiers={(DOMAIN, entry.unique_id)})
    assert device is not None
    assert device.model == "BRAVIA Theatre Quad"


@pytest.mark.usefixtures("mock_bravia_quad_client")
async def test_device_registry_mac_connection(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_bravia_quad_client: MagicMock,
) -> None:
    """Test device registry gets MAC from TCP."""
    mock_config_entry.add_to_hass(hass)

    with patch("custom_components.bravia_quad.PLATFORMS", []):
        await hass.config_entries.async_setup(mock_config_entry.entry_id)
        await hass.async_block_till_done()

    device_registry = dr.async_get(hass)
    device = device_registry.async_get_device(
        identifiers={(DOMAIN, mock_config_entry.unique_id)}
    )
    assert device is not None
    assert (CONNECTION_NETWORK_MAC, "aa:bb:cc:dd:ee:ff") in device.connections


@pytest.mark.usefixtures("mock_bravia_quad_client")
async def test_device_registry_updates_existing_device(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_bravia_quad_client: MagicMock,
) -> None:
    """Test that device info is updated when device already exists with old values."""
    mock_config_entry.add_to_hass(hass)

    # Create device with stale values (simulates prior version of integration)
    device_registry = dr.async_get(hass)
    device_registry.async_get_or_create(
        config_entry_id=mock_config_entry.entry_id,
        identifiers={(DOMAIN, mock_config_entry.unique_id)},
        manufacturer="Sony",
        model="Bravia Theatre",
    )

    # Verify stale values are set
    device = device_registry.async_get_device(
        identifiers={(DOMAIN, mock_config_entry.unique_id)}
    )
    assert device is not None
    assert device.model == "Bravia Theatre"
    assert device.manufacturer == "Sony"

    # Now run setup, which should overwrite with TCP-sourced values
    with patch("custom_components.bravia_quad.PLATFORMS", []):
        await hass.config_entries.async_setup(mock_config_entry.entry_id)
        await hass.async_block_till_done()

    device = device_registry.async_get_device(
        identifiers={(DOMAIN, mock_config_entry.unique_id)}
    )
    assert device is not None
    assert device.model == "BRAVIA Theatre Quad"
    assert device.manufacturer == "SONY"
    assert device.model_id == "HT-A9M2"
    assert device.serial_number == "1234567"
    assert device.sw_version == "001.100"


@pytest.mark.usefixtures("mock_bravia_quad_client")
async def test_backfill_fetches_identity(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_bravia_quad_client: MagicMock,
) -> None:
    """Test that old entries without identity get backfilled on setup."""
    # mock_config_entry has no CONF_MODEL_ID, triggering backfill
    mock_config_entry.add_to_hass(hass)

    with patch("custom_components.bravia_quad.PLATFORMS", []):
        await hass.config_entries.async_setup(mock_config_entry.entry_id)
        await hass.async_block_till_done()

    # Backfill should have fetched permanent identity
    mock_bravia_quad_client.async_get_serial_number.assert_called_once()
    mock_bravia_quad_client.async_get_model_type.assert_called_once()
    mock_bravia_quad_client.async_get_manufacturer.assert_called_once()

    # Firmware version is fetched in _register_device (transient)
    mock_bravia_quad_client.async_get_firmware_version.assert_called_once()

    # Backfilled values should be in entry data
    assert mock_config_entry.data["serial_number"] == "1234567"
    assert mock_config_entry.data["model_id"] == "HT-A9M2"
    assert mock_config_entry.data["model"] == "BRAVIA Theatre Quad"
    assert mock_config_entry.data["manufacturer"] == "SONY"

    # unique_id should be migrated from IP to serial
    assert mock_config_entry.unique_id == "1234567"

    device_registry = dr.async_get(hass)
    device = device_registry.async_get_device(identifiers={(DOMAIN, "1234567")})
    assert device is not None
    assert device.serial_number == "1234567"
    assert (
        device_registry.async_get_device(identifiers={(DOMAIN, "192.168.1.100")})
        is None
    )


@pytest.mark.usefixtures("mock_bravia_quad_client")
async def test_no_backfill_when_identity_present(
    hass: HomeAssistant,
    mock_bravia_quad_client: MagicMock,
) -> None:
    """Test that backfill is skipped when identity is already in entry data."""
    entry = MockConfigEntry(
        title="Bravia Quad",
        domain=DOMAIN,
        data={
            CONF_HOST: "192.168.1.100",
            CONF_HAS_SUBWOOFER: True,
            "model_id": "HT-A9M2",
            "model": "BRAVIA Theatre Quad",
            "manufacturer": "SONY",
            "serial_number": "1234567",
        },
        unique_id="192.168.1.100",
        entry_id="test_no_backfill",
    )
    entry.add_to_hass(hass)

    with patch("custom_components.bravia_quad.PLATFORMS", []):
        await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

    # Backfill getters should NOT be called (identity already present)
    mock_bravia_quad_client.async_get_serial_number.assert_not_called()
    mock_bravia_quad_client.async_get_model_type.assert_not_called()
    mock_bravia_quad_client.async_get_manufacturer.assert_not_called()

    # Firmware version should still be fetched (transient)
    mock_bravia_quad_client.async_get_firmware_version.assert_called_once()


# =============================================================================
# get_device_info Tests
# =============================================================================


def test_get_device_info_returns_identifiers_only() -> None:
    """Test get_device_info returns only identifiers for entity linking."""
    entry = MockConfigEntry(
        title="Bravia Quad",
        domain=DOMAIN,
        data={
            CONF_HOST: "192.168.1.100",
            CONF_HAS_SUBWOOFER: True,
        },
        unique_id="192.168.1.100",
    )

    device_info = get_device_info(entry)

    assert device_info["identifiers"] == {(DOMAIN, "192.168.1.100")}
    # Entity-level DeviceInfo must NOT include metadata that would
    # overwrite the values set by __init__.py during device creation
    assert "manufacturer" not in device_info
    assert "model" not in device_info
    assert "name" not in device_info


def test_get_device_info_without_unique_id_raises() -> None:
    """Test get_device_info raises ValueError when unique_id is None."""
    entry = MockConfigEntry(
        title="Bravia Quad",
        domain=DOMAIN,
        data={
            CONF_HOST: "192.168.1.100",
            CONF_HAS_SUBWOOFER: True,
        },
        unique_id=None,  # No unique_id
    )

    with pytest.raises(ValueError, match="has no unique_id"):
        get_device_info(entry)


# =============================================================================
# migrate_legacy_identifiers Tests
# =============================================================================


async def test_migrate_legacy_identifiers_no_migration_needed_same_ids(
    hass: HomeAssistant,
) -> None:
    """Test migration is skipped when unique_id equals entry_id."""
    entry = MockConfigEntry(
        title="Bravia Quad",
        domain=DOMAIN,
        data={CONF_HOST: "192.168.1.100"},
        unique_id="same_id",
        entry_id="same_id",
    )
    entry.add_to_hass(hass)

    # Should not raise or do anything
    migrate_legacy_identifiers(hass, entry)


async def test_migrate_legacy_identifiers_no_migration_needed_no_unique_id(
    hass: HomeAssistant,
) -> None:
    """Test migration is skipped when unique_id is None."""
    entry = MockConfigEntry(
        title="Bravia Quad",
        domain=DOMAIN,
        data={CONF_HOST: "192.168.1.100"},
        unique_id=None,
        entry_id="test_entry_id",
    )
    entry.add_to_hass(hass)

    # Should not raise or do anything
    migrate_legacy_identifiers(hass, entry)


async def test_migrate_device_identifier(
    hass: HomeAssistant,
) -> None:
    """Test device identifier migration from entry_id to unique_id format."""
    old_entry_id = "old_entry_id"
    new_unique_id = "192.168.1.100"

    entry = MockConfigEntry(
        title="Bravia Quad",
        domain=DOMAIN,
        data={CONF_HOST: "192.168.1.100"},
        unique_id=new_unique_id,
        entry_id=old_entry_id,
    )
    entry.add_to_hass(hass)

    device_registry = dr.async_get(hass)

    # Create a device with old identifier format
    device_registry.async_get_or_create(
        config_entry_id=entry.entry_id,
        identifiers={(DOMAIN, old_entry_id)},
        name="Bravia Quad",
        manufacturer="Sony",
    )

    # Verify old device exists
    old_device = device_registry.async_get_device(identifiers={(DOMAIN, old_entry_id)})
    assert old_device is not None

    # Run migration
    migrate_legacy_identifiers(hass, entry)

    # Old identifier should no longer exist
    old_device_after = device_registry.async_get_device(
        identifiers={(DOMAIN, old_entry_id)}
    )
    assert old_device_after is None

    # New identifier should exist
    new_device = device_registry.async_get_device(identifiers={(DOMAIN, new_unique_id)})
    assert new_device is not None


async def test_migrate_device_when_new_device_exists(
    hass: HomeAssistant,
) -> None:
    """Test device migration removes old device when new device already exists."""
    old_entry_id = "old_entry_id"
    new_unique_id = "192.168.1.100"

    entry = MockConfigEntry(
        title="Bravia Quad",
        domain=DOMAIN,
        data={CONF_HOST: "192.168.1.100"},
        unique_id=new_unique_id,
        entry_id=old_entry_id,
    )
    entry.add_to_hass(hass)

    device_registry = dr.async_get(hass)

    # Create old device with legacy identifier
    old_device = device_registry.async_get_or_create(
        config_entry_id=entry.entry_id,
        identifiers={(DOMAIN, old_entry_id)},
        name="Bravia Quad Old",
        manufacturer="Sony",
    )

    # Create new device with correct identifier
    new_device = device_registry.async_get_or_create(
        config_entry_id=entry.entry_id,
        identifiers={(DOMAIN, new_unique_id)},
        name="Bravia Quad New",
        manufacturer="Sony",
    )

    old_device_id = old_device.id
    new_device_id = new_device.id

    # Run migration
    migrate_legacy_identifiers(hass, entry)

    # Old device should be removed
    assert device_registry.async_get(old_device_id) is None

    # New device should still exist
    assert device_registry.async_get(new_device_id) is not None


async def test_migrate_entity_unique_ids(
    hass: HomeAssistant,
) -> None:
    """Test entity unique_id migration from entry_id to unique_id format."""
    old_entry_id = "old_entry_id"
    new_unique_id = "192.168.1.100"

    entry = MockConfigEntry(
        title="Bravia Quad",
        domain=DOMAIN,
        data={CONF_HOST: "192.168.1.100"},
        unique_id=new_unique_id,
        entry_id=old_entry_id,
    )
    entry.add_to_hass(hass)

    entity_registry = er.async_get(hass)

    # Create entities with old unique_id format
    old_unique_id = f"{DOMAIN}_{old_entry_id}_power"
    entity_registry.async_get_or_create(
        "switch",
        DOMAIN,
        old_unique_id,
        config_entry=entry,
        suggested_object_id="bravia_quad_power",
    )

    # Verify entity exists with old unique_id
    entity_entry = entity_registry.async_get_entity_id("switch", DOMAIN, old_unique_id)
    assert entity_entry is not None

    # Run migration
    migrate_legacy_identifiers(hass, entry)

    # Old unique_id should no longer exist
    old_entity = entity_registry.async_get_entity_id("switch", DOMAIN, old_unique_id)
    assert old_entity is None

    # New unique_id should exist
    new_unique_id_full = f"{DOMAIN}_{new_unique_id}_power"
    new_entity = entity_registry.async_get_entity_id(
        "switch", DOMAIN, new_unique_id_full
    )
    assert new_entity is not None


async def test_migrate_entity_when_new_entity_exists(
    hass: HomeAssistant,
) -> None:
    """Test entity migration removes old entity when new entity already exists."""
    old_entry_id = "old_entry_id"
    new_unique_id = "192.168.1.100"

    entry = MockConfigEntry(
        title="Bravia Quad",
        domain=DOMAIN,
        data={CONF_HOST: "192.168.1.100"},
        unique_id=new_unique_id,
        entry_id=old_entry_id,
    )
    entry.add_to_hass(hass)

    entity_registry = er.async_get(hass)

    # Create entity with old unique_id
    old_unique_id = f"{DOMAIN}_{old_entry_id}_power"
    old_entity = entity_registry.async_get_or_create(
        "switch",
        DOMAIN,
        old_unique_id,
        config_entry=entry,
        suggested_object_id="bravia_quad_power_old",
    )

    # Create entity with new unique_id
    new_unique_id_full = f"{DOMAIN}_{new_unique_id}_power"
    new_entity = entity_registry.async_get_or_create(
        "switch",
        DOMAIN,
        new_unique_id_full,
        config_entry=entry,
        suggested_object_id="bravia_quad_power_new",
    )

    old_entity_id = old_entity.entity_id
    new_entity_id = new_entity.entity_id

    # Run migration
    migrate_legacy_identifiers(hass, entry)

    # Old entity should be removed
    assert entity_registry.async_get(old_entity_id) is None

    # New entity should still exist
    assert entity_registry.async_get(new_entity_id) is not None


async def test_migrate_multiple_entities(
    hass: HomeAssistant,
) -> None:
    """Test migration handles multiple entities correctly."""
    old_entry_id = "old_entry_id"
    new_unique_id = "192.168.1.100"

    entry = MockConfigEntry(
        title="Bravia Quad",
        domain=DOMAIN,
        data={CONF_HOST: "192.168.1.100"},
        unique_id=new_unique_id,
        entry_id=old_entry_id,
    )
    entry.add_to_hass(hass)

    entity_registry = er.async_get(hass)

    # Create multiple entities with old unique_id format
    suffix_to_domain = {
        "power": "switch",
        "volume": "number",
        "input": "select",
    }
    for suffix, domain in suffix_to_domain.items():
        old_unique_id = f"{DOMAIN}_{old_entry_id}_{suffix}"
        entity_registry.async_get_or_create(
            domain,
            DOMAIN,
            old_unique_id,
            config_entry=entry,
        )

    # Run migration
    migrate_legacy_identifiers(hass, entry)

    # All entities should be migrated
    for suffix, domain in suffix_to_domain.items():
        old_unique_id = f"{DOMAIN}_{old_entry_id}_{suffix}"
        new_unique_id_full = f"{DOMAIN}_{new_unique_id}_{suffix}"

        # Old should not exist
        old_entity = entity_registry.async_get_entity_id(domain, DOMAIN, old_unique_id)
        assert old_entity is None

        # New should exist
        new_entity = entity_registry.async_get_entity_id(
            domain, DOMAIN, new_unique_id_full
        )
        assert new_entity is not None


async def test_migrate_skips_non_matching_entities(
    hass: HomeAssistant,
) -> None:
    """Test migration skips entities that don't match the old prefix."""
    old_entry_id = "old_entry_id"
    new_unique_id = "192.168.1.100"

    entry = MockConfigEntry(
        title="Bravia Quad",
        domain=DOMAIN,
        data={CONF_HOST: "192.168.1.100"},
        unique_id=new_unique_id,
        entry_id=old_entry_id,
    )
    entry.add_to_hass(hass)

    entity_registry = er.async_get(hass)

    # Create entity with a different prefix (already migrated or different format)
    other_unique_id = f"{DOMAIN}_some_other_id_power"
    entity_registry.async_get_or_create(
        "switch",
        DOMAIN,
        other_unique_id,
        config_entry=entry,
    )

    # Run migration
    migrate_legacy_identifiers(hass, entry)

    # Entity should remain unchanged
    entity = entity_registry.async_get_entity_id("switch", DOMAIN, other_unique_id)
    assert entity is not None


async def test_migrate_no_old_device(
    hass: HomeAssistant,
) -> None:
    """Test migration handles case when no old device exists."""
    entry = MockConfigEntry(
        title="Bravia Quad",
        domain=DOMAIN,
        data={CONF_HOST: "192.168.1.100"},
        unique_id="192.168.1.100",
        entry_id="old_entry_id",
    )
    entry.add_to_hass(hass)

    # No device created - migration should handle gracefully
    migrate_legacy_identifiers(hass, entry)  # Should not raise


async def test_migrate_from_ip_based_device_and_entities(
    hass: HomeAssistant,
) -> None:
    """Test migration from IP-based device identifier and entity prefix."""
    legacy_ip = "192.168.1.100"
    target_serial = "1234567"

    entry = MockConfigEntry(
        title="Bravia Quad",
        domain=DOMAIN,
        data={CONF_HOST: legacy_ip, CONF_HAS_SUBWOOFER: True},
        unique_id=target_serial,
        entry_id="test_ip_migration",
    )
    entry.add_to_hass(hass)

    device_registry = dr.async_get(hass)
    device_registry.async_get_or_create(
        config_entry_id=entry.entry_id,
        identifiers={(DOMAIN, legacy_ip)},
        name="Bravia Quad",
    )

    entity_registry = er.async_get(hass)
    old_unique_id = f"{DOMAIN}_{legacy_ip}_power"
    entity_registry.async_get_or_create(
        "switch",
        DOMAIN,
        old_unique_id,
        config_entry=entry,
    )

    migrate_legacy_identifiers(hass, entry)

    assert device_registry.async_get_device(identifiers={(DOMAIN, legacy_ip)}) is None
    assert (
        device_registry.async_get_device(identifiers={(DOMAIN, target_serial)})
        is not None
    )
    assert entity_registry.async_get_entity_id("switch", DOMAIN, old_unique_id) is None
    assert (
        entity_registry.async_get_entity_id(
            "switch", DOMAIN, f"{DOMAIN}_{target_serial}_power"
        )
        is not None
    )


async def test_migrate_from_mac_based_device_and_entities(
    hass: HomeAssistant,
) -> None:
    """Test migration from MAC-based device identifier and entity prefix."""
    legacy_mac = "60:ff:9e:12:34:56"
    target_serial = "1234567"

    entry = MockConfigEntry(
        title="Bravia Quad",
        domain=DOMAIN,
        data={
            CONF_HOST: "192.168.1.100",
            CONF_MAC: legacy_mac,
            CONF_HAS_SUBWOOFER: True,
        },
        unique_id=target_serial,
        entry_id="test_mac_migration",
    )
    entry.add_to_hass(hass)

    device_registry = dr.async_get(hass)
    device_registry.async_get_or_create(
        config_entry_id=entry.entry_id,
        identifiers={(DOMAIN, legacy_mac)},
        name="Bravia Quad",
    )

    entity_registry = er.async_get(hass)
    old_unique_id = f"{DOMAIN}_{legacy_mac}_power"
    entity_registry.async_get_or_create(
        "switch",
        DOMAIN,
        old_unique_id,
        config_entry=entry,
    )

    migrate_legacy_identifiers(hass, entry)

    assert device_registry.async_get_device(identifiers={(DOMAIN, legacy_mac)}) is None
    assert (
        device_registry.async_get_device(identifiers={(DOMAIN, target_serial)})
        is not None
    )
    assert entity_registry.async_get_entity_id("switch", DOMAIN, old_unique_id) is None
    assert (
        entity_registry.async_get_entity_id(
            "switch", DOMAIN, f"{DOMAIN}_{target_serial}_power"
        )
        is not None
    )


async def test_migrate_removes_duplicate_when_serial_entity_already_exists(
    hass: HomeAssistant,
) -> None:
    """Test botched upgrade dedup removes legacy entity when serial entity exists."""
    legacy_ip = "192.168.1.100"
    target_serial = "1234567"

    entry = MockConfigEntry(
        title="Bravia Quad",
        domain=DOMAIN,
        data={CONF_HOST: legacy_ip, CONF_HAS_SUBWOOFER: True},
        unique_id=target_serial,
        entry_id="test_dedup",
    )
    entry.add_to_hass(hass)

    entity_registry = er.async_get(hass)
    old_unique_id = f"{DOMAIN}_{legacy_ip}_power"
    new_unique_id = f"{DOMAIN}_{target_serial}_power"
    old_entity = entity_registry.async_get_or_create(
        "switch",
        DOMAIN,
        old_unique_id,
        config_entry=entry,
        suggested_object_id="bravia_theatre_power",
    )
    new_entity = entity_registry.async_get_or_create(
        "switch",
        DOMAIN,
        new_unique_id,
        config_entry=entry,
        suggested_object_id="bravia_theatre_power_2",
    )

    migrate_legacy_identifiers(hass, entry)

    assert entity_registry.async_get(old_entity.entity_id) is None
    assert entity_registry.async_get(new_entity.entity_id) is not None


@pytest.mark.usefixtures("mock_bravia_quad_client")
async def test_setup_ip_entry_migrates_without_duplicates(
    hass: HomeAssistant,
    mock_bravia_quad_client: MagicMock,
) -> None:
    """Test full setup migrates IP-based legacy entities without duplicating."""
    legacy_ip = "192.168.1.100"
    target_serial = "1234567"

    entry = MockConfigEntry(
        title="Bravia Quad",
        domain=DOMAIN,
        data={CONF_HOST: legacy_ip, CONF_HAS_SUBWOOFER: True},
        unique_id=legacy_ip,
        entry_id="test_setup_migration",
    )
    entry.add_to_hass(hass)

    device_registry = dr.async_get(hass)
    device_registry.async_get_or_create(
        config_entry_id=entry.entry_id,
        identifiers={(DOMAIN, legacy_ip)},
        name="Bravia Quad",
    )

    entity_registry = er.async_get(hass)
    legacy_suffixes = ("power", "volume", "input")
    for suffix in legacy_suffixes:
        entity_registry.async_get_or_create(
            "switch"
            if suffix == "power"
            else "number"
            if suffix == "volume"
            else "select",
            DOMAIN,
            f"{DOMAIN}_{legacy_ip}_{suffix}",
            config_entry=entry,
        )

    with patch("custom_components.bravia_quad.PLATFORMS", [Platform.SWITCH]):
        await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

    assert entry.unique_id == target_serial

    assert device_registry.async_get_device(identifiers={(DOMAIN, legacy_ip)}) is None
    assert (
        device_registry.async_get_device(identifiers={(DOMAIN, target_serial)})
        is not None
    )

    bravia_entities = [
        e
        for e in entity_registry.entities.values()
        if e.platform == DOMAIN and e.config_entry_id == entry.entry_id
    ]
    ip_entities = [e for e in bravia_entities if legacy_ip in (e.unique_id or "")]
    assert not ip_entities

    power_entities = [
        e for e in bravia_entities if e.unique_id and e.unique_id.endswith("_power")
    ]
    assert len(power_entities) == 1
    assert power_entities[0].unique_id == f"{DOMAIN}_{target_serial}_power"


# =============================================================================
# verify_feature_value Tests
# =============================================================================


def test_verify_feature_value_match() -> None:
    """Test verify_feature_value returns actual when values match."""
    assert (
        verify_feature_value(
            requested="on",
            actual="on",
            feature_label="test feature",
        )
        == "on"
    )


def test_verify_feature_value_mismatch_raises() -> None:
    """Test verify_feature_value raises on mismatch."""
    with pytest.raises(HomeAssistantError) as exc_info:
        verify_feature_value(
            requested="off",
            actual="on",
            feature_label="test feature",
        )
    assert exc_info.value.translation_key == "verify_value_mismatch"


def test_verify_feature_value_mismatch_with_hint() -> None:
    """Test verify_feature_value includes hint in mismatch error."""
    with pytest.raises(HomeAssistantError) as exc_info:
        verify_feature_value(
            requested="earc",
            actual="arc",
            feature_label="audio return channel",
            mismatch_hint="hint text",
        )
    assert exc_info.value.translation_key == "verify_value_mismatch_hint"
    assert exc_info.value.translation_placeholders["hint"] == "hint text"


def test_verify_feature_value_none_actual_raises() -> None:
    """Test verify_feature_value raises when actual is None."""
    with pytest.raises(HomeAssistantError) as exc_info:
        verify_feature_value(
            requested="off",
            actual=None,
            feature_label="external control",
        )
    assert exc_info.value.translation_key == "verify_read_failed"


def test_verify_feature_value_invalid_actual_raises() -> None:
    """Test verify_feature_value raises when actual is not in valid_values."""
    with pytest.raises(HomeAssistantError, match="unexpected"):
        verify_feature_value(
            requested="on",
            actual="invalid",
            feature_label="IMAX mode",
            valid_values={"auto", "on", "off"},
        )


def test_verify_feature_value_int() -> None:
    """Test verify_feature_value works with integer values."""
    assert (
        verify_feature_value(
            requested=10,
            actual=10,
            feature_label="AV sync",
        )
        == 10
    )


# =============================================================================
# BraviaQuadNotificationMixin Tests
# =============================================================================


async def test_notification_mixin_registers_callback(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_bravia_quad_client: MagicMock,
) -> None:
    """Test that notification mixin registers callback on async_added_to_hass."""
    mock_config_entry.add_to_hass(hass)

    with patch("custom_components.bravia_quad.PLATFORMS", [Platform.SWITCH]):
        await hass.config_entries.async_setup(mock_config_entry.entry_id)
        await hass.async_block_till_done()

    # Verify callbacks were registered
    assert mock_bravia_quad_client.register_notification_callback.called


async def test_notification_mixin_unregisters_callback_on_remove(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_bravia_quad_client: MagicMock,
) -> None:
    """Test that notification mixin unregisters callback on entity removal."""
    mock_config_entry.add_to_hass(hass)

    with patch("custom_components.bravia_quad.PLATFORMS", [Platform.SWITCH]):
        await hass.config_entries.async_setup(mock_config_entry.entry_id)
        await hass.async_block_till_done()

    # Unload the entry
    await hass.config_entries.async_unload(mock_config_entry.entry_id)
    await hass.async_block_till_done()

    # Verify callbacks were unregistered
    assert mock_bravia_quad_client.unregister_notification_callback.called
