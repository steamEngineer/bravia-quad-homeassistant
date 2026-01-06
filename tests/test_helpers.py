"""Tests for the Bravia Quad helpers module."""

from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import MagicMock, patch

import pytest
from homeassistant.const import CONF_HOST, CONF_MAC, CONF_NAME, Platform
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.device_registry import CONNECTION_NETWORK_MAC
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.bravia_quad.const import (
    CONF_HAS_SUBWOOFER,
    CONF_MODEL,
    DEFAULT_MODEL,
    DOMAIN,
)
from custom_components.bravia_quad.helpers import (
    get_device_info,
    migrate_legacy_identifiers,
)

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant


# =============================================================================
# get_device_info Tests
# =============================================================================


def test_get_device_info_basic() -> None:
    """Test get_device_info with basic config entry."""
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
    assert device_info["name"] == DEFAULT_MODEL
    assert device_info["manufacturer"] == "Sony"
    assert device_info["model"] == DEFAULT_MODEL
    assert device_info["configuration_url"] == "http://192.168.1.100"
    # No MAC address, so connections should be empty
    assert device_info["connections"] == set()


def test_get_device_info_with_mac() -> None:
    """Test get_device_info with MAC address."""
    entry = MockConfigEntry(
        title="Bravia Quad",
        domain=DOMAIN,
        data={
            CONF_HOST: "192.168.1.100",
            CONF_MAC: "aa:bb:cc:dd:ee:ff",
            CONF_HAS_SUBWOOFER: True,
        },
        unique_id="192.168.1.100",
    )

    device_info = get_device_info(entry)

    assert device_info["connections"] == {(CONNECTION_NETWORK_MAC, "aa:bb:cc:dd:ee:ff")}


def test_get_device_info_with_custom_name_and_model() -> None:
    """Test get_device_info with custom name and model."""
    entry = MockConfigEntry(
        title="My Bravia",
        domain=DOMAIN,
        data={
            CONF_HOST: "192.168.1.100",
            CONF_NAME: "Living Room Speaker",
            CONF_MODEL: "HT-A9000",
            CONF_HAS_SUBWOOFER: False,
        },
        unique_id="192.168.1.100",
    )

    device_info = get_device_info(entry)

    assert device_info["name"] == "Living Room Speaker"
    assert device_info["model"] == "HT-A9000"


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
