"""Tests for gRPC subwoofer detection apply / setup recompute."""

from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from homeassistant.const import CONF_HOST
from homeassistant.exceptions import HomeAssistantError
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.bravia_quad import _async_recompute_grpc_subwoofer
from custom_components.bravia_quad.button import BraviaGrpcDetectSubwooferButton
from custom_components.bravia_quad.const import (
    CONF_HAS_SUBWOOFER,
    CONF_TRANSPORT,
    DOMAIN,
    TRANSPORT_GRPC,
)
from custom_components.bravia_quad.helpers import async_apply_has_subwoofer
from custom_components.bravia_quad.transport import GRPC_PATH_SW_STATUS

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant


@pytest.fixture
def grpc_entry(hass: HomeAssistant) -> MockConfigEntry:
    entry = MockConfigEntry(
        title="Office Quads",
        domain=DOMAIN,
        data={
            CONF_HOST: "192.168.1.100",
            CONF_TRANSPORT: TRANSPORT_GRPC,
            CONF_HAS_SUBWOOFER: False,
        },
        unique_id="8804927",
    )
    entry.add_to_hass(hass)
    return entry


async def test_async_apply_has_subwoofer_noop_when_unchanged(
    hass: HomeAssistant, grpc_entry: MockConfigEntry
) -> None:
    changed = await async_apply_has_subwoofer(hass, grpc_entry, has_subwoofer=False)
    assert changed is False


async def test_async_apply_has_subwoofer_updates_without_reload(
    hass: HomeAssistant, grpc_entry: MockConfigEntry
) -> None:
    with patch.object(
        hass.config_entries, "async_reload", new=AsyncMock(return_value=True)
    ) as reload:
        changed = await async_apply_has_subwoofer(hass, grpc_entry, has_subwoofer=True)

    assert changed is True
    assert grpc_entry.data[CONF_HAS_SUBWOOFER] is True
    reload.assert_not_awaited()


async def test_async_apply_has_subwoofer_reload_when_requested(
    hass: HomeAssistant, grpc_entry: MockConfigEntry
) -> None:
    with patch.object(
        hass.config_entries, "async_reload", new=AsyncMock(return_value=True)
    ) as reload:
        changed = await async_apply_has_subwoofer(
            hass, grpc_entry, has_subwoofer=True, reload=True
        )

    assert changed is True
    reload.assert_awaited_once_with(grpc_entry.entry_id)


async def test_async_apply_has_subwoofer_reload_failure(
    hass: HomeAssistant, grpc_entry: MockConfigEntry
) -> None:
    with (
        patch.object(
            hass.config_entries, "async_reload", new=AsyncMock(return_value=False)
        ),
        pytest.raises(HomeAssistantError),
    ):
        await async_apply_has_subwoofer(
            hass, grpc_entry, has_subwoofer=True, reload=True
        )


async def test_recompute_grpc_subwoofer_at_setup(
    hass: HomeAssistant, grpc_entry: MockConfigEntry
) -> None:
    grpc_client = MagicMock()
    grpc_client.notify_state = {GRPC_PATH_SW_STATUS: "connected"}

    await _async_recompute_grpc_subwoofer(hass, grpc_entry, grpc_client)

    assert grpc_entry.data[CONF_HAS_SUBWOOFER] is True


async def test_grpc_detect_button_updates_flag(
    hass: HomeAssistant, grpc_entry: MockConfigEntry
) -> None:
    grpc_client = MagicMock()
    grpc_client.async_get_states_dict = AsyncMock(
        return_value={GRPC_PATH_SW_STATUS: "connected"}
    )
    grpc_client.async_get_states_app_sequence = AsyncMock(return_value=None)

    button = BraviaGrpcDetectSubwooferButton(hass, grpc_client, grpc_entry)
    await button.async_press()

    assert grpc_entry.data[CONF_HAS_SUBWOOFER] is True
