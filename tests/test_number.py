"""Tests for the Bravia Quad number platform."""

from __future__ import annotations

import asyncio
import contextlib
from typing import TYPE_CHECKING
from unittest.mock import AsyncMock, patch

import pytest
from homeassistant.const import ATTR_ENTITY_ID, Platform
from homeassistant.helpers import entity_registry as er

from .conftest import get_entity_id_by_unique_id_suffix

if TYPE_CHECKING:
    from unittest.mock import MagicMock

    from homeassistant.core import HomeAssistant
    from pytest_homeassistant_custom_component.common import MockConfigEntry

NUMBER_DOMAIN = "number"


@pytest.fixture
def platforms() -> list[Platform]:
    """Return the platforms to be loaded for this test."""
    return [Platform.NUMBER]


@pytest.mark.usefixtures("init_integration")
async def test_number_entities(
    hass: HomeAssistant,
    entity_registry: er.EntityRegistry,
) -> None:
    """Test number entities are created correctly."""
    # Verify expected number entities exist (with subwoofer)
    expected_entities = {
        "_volume": "50",
        "_rear_level": "0",
        "_bass_level_slider": "0",
        "_volume_step_interval": "0",
    }

    for suffix, expected_state in expected_entities.items():
        entity_id = get_entity_id_by_unique_id_suffix(entity_registry, suffix)
        assert entity_id is not None, f"Entity with suffix {suffix} not found"

        state = hass.states.get(entity_id)
        assert state is not None, f"State for {entity_id} not found"
        assert state.state == expected_state, f"Expected {expected_state} for {suffix}"


@pytest.mark.usefixtures("init_integration")
async def test_volume_number_set_value(
    hass: HomeAssistant,
    mock_bravia_quad_client: MagicMock,
    entity_registry: er.EntityRegistry,
) -> None:
    """Test setting the volume value."""
    entity_id = get_entity_id_by_unique_id_suffix(entity_registry, "_volume")
    assert entity_id is not None

    # Verify initial state
    state = hass.states.get(entity_id)
    assert state is not None
    assert state.state == "50"  # Mock default value

    mock_bravia_quad_client.async_set_volume.return_value = True

    await hass.services.async_call(
        NUMBER_DOMAIN,
        "set_value",
        {ATTR_ENTITY_ID: entity_id, "value": 75},
        blocking=True,
    )

    mock_bravia_quad_client.async_set_volume.assert_called_once_with(75)


@pytest.mark.usefixtures("init_integration")
async def test_rear_level_number_set_value(
    hass: HomeAssistant,
    mock_bravia_quad_client: MagicMock,
    entity_registry: er.EntityRegistry,
) -> None:
    """Test setting the rear level value."""
    entity_id = get_entity_id_by_unique_id_suffix(entity_registry, "_rear_level")
    assert entity_id is not None

    # Verify initial state
    state = hass.states.get(entity_id)
    assert state is not None
    assert state.state == "0"  # Mock default value

    mock_bravia_quad_client.async_set_rear_level.return_value = True

    await hass.services.async_call(
        NUMBER_DOMAIN,
        "set_value",
        {ATTR_ENTITY_ID: entity_id, "value": 5},
        blocking=True,
    )

    mock_bravia_quad_client.async_set_rear_level.assert_called_once_with(5)


@pytest.mark.usefixtures("init_integration")
async def test_bass_level_number_set_value(
    hass: HomeAssistant,
    mock_bravia_quad_client: MagicMock,
    entity_registry: er.EntityRegistry,
) -> None:
    """Test setting the bass level value (with subwoofer)."""
    entity_id = get_entity_id_by_unique_id_suffix(entity_registry, "_bass_level_slider")
    assert entity_id is not None

    # Verify initial state (bass level slider is created when has_subwoofer=True)
    state = hass.states.get(entity_id)
    assert state is not None
    assert state.state == "0"  # Mock default value

    mock_bravia_quad_client.async_set_bass_level.return_value = True

    await hass.services.async_call(
        NUMBER_DOMAIN,
        "set_value",
        {ATTR_ENTITY_ID: entity_id, "value": 3},
        blocking=True,
    )

    mock_bravia_quad_client.async_set_bass_level.assert_called_once_with(3)


@pytest.mark.usefixtures("init_integration")
async def test_volume_step_interval_number_set_value(
    hass: HomeAssistant,
    mock_bravia_quad_client: MagicMock,
    entity_registry: er.EntityRegistry,
) -> None:
    """Test setting the volume step interval value."""
    entity_id = get_entity_id_by_unique_id_suffix(
        entity_registry, "_volume_step_interval"
    )
    assert entity_id is not None

    # Verify initial state
    state = hass.states.get(entity_id)
    assert state is not None
    assert state.state == "0"

    await hass.services.async_call(
        NUMBER_DOMAIN,
        "set_value",
        {ATTR_ENTITY_ID: entity_id, "value": 500},
        blocking=True,
    )

    assert mock_bravia_quad_client.volume_step_interval == 500
    state = hass.states.get(entity_id)
    assert state.state == "500.0"


@pytest.mark.usefixtures("init_integration")
async def test_volume_step_interval_logic(
    hass: HomeAssistant,
    mock_bravia_quad_client: MagicMock,
    entity_registry: er.EntityRegistry,
) -> None:
    """Test volume step interval logic."""
    volume_id = get_entity_id_by_unique_id_suffix(entity_registry, "_volume")
    interval_id = get_entity_id_by_unique_id_suffix(
        entity_registry, "_volume_step_interval"
    )

    # Set interval to 100ms
    await hass.services.async_call(
        NUMBER_DOMAIN,
        "set_value",
        {ATTR_ENTITY_ID: interval_id, "value": 100},
        blocking=True,
    )
    assert mock_bravia_quad_client.volume_step_interval == 100

    # Set volume from 50 to 52 (2 steps)
    mock_bravia_quad_client.async_set_volume.return_value = True

    # We need to patch sleep to avoid waiting
    with patch(
        "custom_components.bravia_quad.number.asyncio.sleep", new_callable=AsyncMock
    ) as mock_sleep:
        await hass.services.async_call(
            NUMBER_DOMAIN,
            "set_value",
            {ATTR_ENTITY_ID: volume_id, "value": 52},
            blocking=True,
        )
        # Wait for the background task to complete
        await hass.async_block_till_done()

    # Should have called sleep(0.1) twice (before each step)
    # Note: call_count might be higher if other parts of the system call sleep
    assert mock_sleep.call_count >= 2
    assert mock_sleep.call_args_list[0][0][0] == 0.1
    assert mock_sleep.call_args_list[1][0][0] == 0.1

    # Should have called async_set_volume for each step: 51, 52
    assert mock_bravia_quad_client.async_set_volume.call_count == 2
    mock_bravia_quad_client.async_set_volume.assert_any_call(51)
    mock_bravia_quad_client.async_set_volume.assert_any_call(52)


@pytest.mark.usefixtures("init_integration")
async def test_volume_step_interval_race_condition(
    hass: HomeAssistant,
    mock_bravia_quad_client: MagicMock,
    entity_registry: er.EntityRegistry,
) -> None:
    """Test race condition where multiple transitions are started."""
    volume_id = get_entity_id_by_unique_id_suffix(entity_registry, "_volume")
    interval_id = get_entity_id_by_unique_id_suffix(
        entity_registry, "_volume_step_interval"
    )

    # Set interval to 1000ms
    await hass.services.async_call(
        NUMBER_DOMAIN,
        "set_value",
        {ATTR_ENTITY_ID: interval_id, "value": 1000},
        blocking=True,
    )

    # Track how many transitions are active
    active_transitions = 0
    max_active_transitions = 0

    async def mock_set_volume(val: int) -> bool:
        nonlocal active_transitions, max_active_transitions
        active_transitions += 1
        max_active_transitions = max(max_active_transitions, active_transitions)
        await asyncio.sleep(0.01)
        active_transitions -= 1
        return True

    mock_bravia_quad_client.async_set_volume.side_effect = mock_set_volume

    # Start first transition
    await hass.services.async_call(
        NUMBER_DOMAIN,
        "set_value",
        {ATTR_ENTITY_ID: volume_id, "value": 60},
        blocking=True,
    )
    await asyncio.sleep(0.02)

    # Start second transition immediately
    await hass.services.async_call(
        NUMBER_DOMAIN,
        "set_value",
        {ATTR_ENTITY_ID: volume_id, "value": 70},
        blocking=True,
    )
    await asyncio.sleep(0.02)

    # Start third transition
    await hass.services.async_call(
        NUMBER_DOMAIN,
        "set_value",
        {ATTR_ENTITY_ID: volume_id, "value": 80},
        blocking=True,
    )

    # Wait for all transitions to complete
    await hass.async_block_till_done()

    assert max_active_transitions == 1


@pytest.fixture
def platforms_no_subwoofer() -> list[Platform]:
    """Return the platforms to be loaded for this test."""
    return [Platform.NUMBER]


@pytest.mark.usefixtures("mock_bravia_quad_client")
async def test_bass_level_not_created_without_subwoofer(
    hass: HomeAssistant,
    mock_config_entry_no_subwoofer: MockConfigEntry,
    platforms_no_subwoofer: list[Platform],
    entity_registry: er.EntityRegistry,
) -> None:
    """Test that bass level slider is not created without subwoofer."""
    mock_config_entry_no_subwoofer.add_to_hass(hass)

    with patch("custom_components.bravia_quad.PLATFORMS", platforms_no_subwoofer):
        await hass.config_entries.async_setup(mock_config_entry_no_subwoofer.entry_id)
        await hass.async_block_till_done()

    # Bass level slider should NOT exist when subwoofer is not present
    entity_id = get_entity_id_by_unique_id_suffix(entity_registry, "_bass_level_slider")
    assert entity_id is None


@pytest.mark.usefixtures("init_integration")
async def test_volume_step_interval_cancellation_on_remove(
    hass: HomeAssistant,
    mock_bravia_quad_client: MagicMock,
    entity_registry: er.EntityRegistry,
) -> None:
    """Test volume transition is cancelled when entity is removed."""
    volume_id = get_entity_id_by_unique_id_suffix(entity_registry, "_volume")
    interval_id = get_entity_id_by_unique_id_suffix(
        entity_registry, "_volume_step_interval"
    )

    # Set interval to 1ms to quickly pass the loop sleep
    await hass.services.async_call(
        NUMBER_DOMAIN,
        "set_value",
        {ATTR_ENTITY_ID: interval_id, "value": 1},
        blocking=True,
    )

    # Track if transition was cancelled
    cancelled = False

    async def mock_set_volume(val: int) -> bool:
        nonlocal cancelled
        try:
            await asyncio.sleep(1)
        except asyncio.CancelledError:
            cancelled = True
            raise
        else:
            return True

    mock_bravia_quad_client.async_set_volume.side_effect = mock_set_volume

    # Start transition
    await hass.services.async_call(
        NUMBER_DOMAIN,
        "set_value",
        {ATTR_ENTITY_ID: volume_id, "value": 60},
        blocking=False,
    )

    # Give it a moment to start the task
    await asyncio.sleep(0.05)

    # Get the entity object
    component = hass.data["number"]
    entity = next(ent for ent in component.entities if ent.entity_id == volume_id)

    assert entity._transition_task is not None  # noqa: SLF001
    task = entity._transition_task  # noqa: SLF001

    # Remove the entity (simulating removal from HA)
    await entity.async_will_remove_from_hass()

    # Wait for the task to be cancelled
    with contextlib.suppress(asyncio.CancelledError):
        await asyncio.wait_for(task, timeout=0.1)

    # The task should be cancelled
    assert task.cancelled() or task.done()
    assert entity._transition_task is None  # noqa: SLF001
    assert cancelled is True


@pytest.mark.usefixtures("init_integration")
async def test_volume_slider_does_not_update_during_transition(
    hass: HomeAssistant,
    mock_bravia_quad_client: MagicMock,
    entity_registry: er.EntityRegistry,
) -> None:
    """Test that slider doesn't update from notifications during transition."""
    volume_id = get_entity_id_by_unique_id_suffix(entity_registry, "_volume")
    interval_id = get_entity_id_by_unique_id_suffix(
        entity_registry, "_volume_step_interval"
    )
    assert volume_id is not None
    assert interval_id is not None

    # Set interval to 100ms
    await hass.services.async_call(
        NUMBER_DOMAIN,
        "set_value",
        {ATTR_ENTITY_ID: interval_id, "value": 100},
        blocking=True,
    )

    # Get the entity object to access internal state and notification handler
    component = hass.data["number"]
    entity = next(ent for ent in component.entities if ent.entity_id == volume_id)

    # Control when volume steps complete
    step_event = asyncio.Event()

    async def slow_set_volume(val: int) -> bool:
        await step_event.wait()
        step_event.clear()
        return True

    mock_bravia_quad_client.async_set_volume.side_effect = slow_set_volume

    # Start transition from 50 to 53 (3 steps)
    await hass.services.async_call(
        NUMBER_DOMAIN,
        "set_value",
        {ATTR_ENTITY_ID: volume_id, "value": 53},
        blocking=True,
    )

    # The slider should immediately show target value
    state = hass.states.get(volume_id)
    assert state is not None
    assert state.state == "53"

    # Verify transition is in progress
    assert entity._transition_in_progress is True  # noqa: SLF001

    # Simulate device sending back notification with intermediate value
    # This should be ignored during transition
    await entity._on_notification(51)  # noqa: SLF001

    # State should still be target value, not the notification value
    state = hass.states.get(volume_id)
    assert state is not None
    assert state.state == "53"

    # Complete all steps
    for _ in range(3):
        step_event.set()
        await asyncio.sleep(0.15)  # Wait for sleep + step

    await hass.async_block_till_done()

    # Transition should be complete
    assert entity._transition_in_progress is False  # noqa: SLF001

    # Now notifications should update the state
    await entity._on_notification(55)  # noqa: SLF001
    state = hass.states.get(volume_id)
    assert state is not None
    assert state.state == "55"


@pytest.mark.usefixtures("init_integration")
async def test_volume_transition_sets_target_immediately(
    hass: HomeAssistant,
    mock_bravia_quad_client: MagicMock,
    entity_registry: er.EntityRegistry,
) -> None:
    """Test that slider shows target value immediately when transition starts."""
    volume_id = get_entity_id_by_unique_id_suffix(entity_registry, "_volume")
    interval_id = get_entity_id_by_unique_id_suffix(
        entity_registry, "_volume_step_interval"
    )
    assert volume_id is not None
    assert interval_id is not None

    # Set interval to 500ms (long enough to observe)
    await hass.services.async_call(
        NUMBER_DOMAIN,
        "set_value",
        {ATTR_ENTITY_ID: interval_id, "value": 500},
        blocking=True,
    )

    # Block volume commands so transition stays active
    volume_blocked = asyncio.Event()

    async def blocked_set_volume(val: int) -> bool:
        await volume_blocked.wait()
        return True

    mock_bravia_quad_client.async_set_volume.side_effect = blocked_set_volume

    # Initial state is 50
    state = hass.states.get(volume_id)
    assert state is not None
    assert state.state == "50"

    # Start transition to 60
    await hass.services.async_call(
        NUMBER_DOMAIN,
        "set_value",
        {ATTR_ENTITY_ID: volume_id, "value": 60},
        blocking=True,
    )

    # State should immediately be 60 (the target), not 50
    state = hass.states.get(volume_id)
    assert state is not None
    assert state.state == "60"

    # Unblock and cleanup
    volume_blocked.set()
    await hass.async_block_till_done()


@pytest.mark.usefixtures("init_integration")
async def test_volume_transition_flag_reset_on_cancel(
    hass: HomeAssistant,
    mock_bravia_quad_client: MagicMock,
    entity_registry: er.EntityRegistry,
) -> None:
    """Test transition_in_progress flag is reset when transition is cancelled."""
    volume_id = get_entity_id_by_unique_id_suffix(entity_registry, "_volume")
    interval_id = get_entity_id_by_unique_id_suffix(
        entity_registry, "_volume_step_interval"
    )
    assert volume_id is not None
    assert interval_id is not None

    # Set interval to 500ms
    await hass.services.async_call(
        NUMBER_DOMAIN,
        "set_value",
        {ATTR_ENTITY_ID: interval_id, "value": 500},
        blocking=True,
    )

    # Block volume commands
    volume_blocked = asyncio.Event()

    async def blocked_set_volume(val: int) -> bool:
        await volume_blocked.wait()
        return True

    mock_bravia_quad_client.async_set_volume.side_effect = blocked_set_volume

    # Get the entity object
    component = hass.data["number"]
    entity = next(ent for ent in component.entities if ent.entity_id == volume_id)

    # Start first transition
    await hass.services.async_call(
        NUMBER_DOMAIN,
        "set_value",
        {ATTR_ENTITY_ID: volume_id, "value": 60},
        blocking=True,
    )

    assert entity._transition_in_progress is True  # noqa: SLF001

    # Start second transition (should cancel the first)
    mock_bravia_quad_client.async_set_volume.reset_mock()
    mock_bravia_quad_client.async_set_volume.return_value = True
    mock_bravia_quad_client.async_set_volume.side_effect = None

    # This new call with interval=0 should just set directly
    await hass.services.async_call(
        NUMBER_DOMAIN,
        "set_value",
        {ATTR_ENTITY_ID: interval_id, "value": 0},
        blocking=True,
    )

    await hass.services.async_call(
        NUMBER_DOMAIN,
        "set_value",
        {ATTR_ENTITY_ID: volume_id, "value": 70},
        blocking=True,
    )

    # With interval=0, no transition should be in progress
    assert entity._transition_in_progress is False  # noqa: SLF001

    # Cleanup
    volume_blocked.set()
    await hass.async_block_till_done()


@pytest.mark.usefixtures("init_integration")
async def test_volume_notification_accepted_after_transition(
    hass: HomeAssistant,
    mock_bravia_quad_client: MagicMock,
    entity_registry: er.EntityRegistry,
) -> None:
    """Test notifications are accepted after transition completes."""
    volume_id = get_entity_id_by_unique_id_suffix(entity_registry, "_volume")
    assert volume_id is not None

    # Set interval directly on the mock client
    mock_bravia_quad_client.volume_step_interval = 10
    mock_bravia_quad_client.async_set_volume.return_value = True

    # Get the entity object
    component = hass.data["number"]
    entity = next(ent for ent in component.entities if ent.entity_id == volume_id)

    # Start transition from 50 to 52 (2 steps)
    with patch(
        "custom_components.bravia_quad.number.asyncio.sleep", new_callable=AsyncMock
    ):
        await hass.services.async_call(
            NUMBER_DOMAIN,
            "set_value",
            {ATTR_ENTITY_ID: volume_id, "value": 52},
            blocking=True,
        )
        # Wait for the transition task to complete within the patch context
        if entity._transition_task:  # noqa: SLF001
            await entity._transition_task  # noqa: SLF001

    # Transition should be complete
    assert entity._transition_in_progress is False  # noqa: SLF001

    # Now a notification should update the state
    await entity._on_notification(45)  # noqa: SLF001
    state = hass.states.get(volume_id)
    assert state is not None
    assert state.state == "45"
