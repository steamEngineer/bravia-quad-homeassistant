"""Mapping-driven gRPC entities for TCP parity in gRPC transport mode."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from homeassistant.components.number import NumberEntity, NumberMode
from homeassistant.components.select import SelectEntity
from homeassistant.components.sensor import SensorEntity
from homeassistant.components.switch import SwitchEntity
from homeassistant.const import EntityCategory, UnitOfTime
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.restore_state import RestoreEntity

from .const import (
    AV_SYNC_STEP,
    BASS_LEVEL_OPTIONS,
    BASS_LEVEL_VALUES_TO_OPTIONS,
    DOMAIN,
    FEATURE_AV_SYNC,
    FEATURE_BASS_LEVEL,
    FEATURE_REAR_LEVEL,
    FEATURE_TV_AV_SYNC,
    FEATURE_VOICE_ZOOM_LEVEL,
    MAX_AV_SYNC,
    MAX_BASS_LEVEL,
    MAX_REAR_LEVEL,
    MAX_VOICE_ZOOM_LEVEL,
    MAX_VOLUME,
    MIN_AV_SYNC,
    MIN_BASS_LEVEL,
    MIN_REAR_LEVEL,
    MIN_VOICE_ZOOM_LEVEL,
)
from .entity import (
    BraviaGrpcPathMixin,
    BraviaQuadVolumeStepIntervalNumber,
    entity_unique_id,
    get_device_info,
)
from .grpc.get_capabilities_response import (
    CapabilityMeta,
    int_range_from_capability,
)
from .grpc_entity_registry import EntitySpec, entity_spec_for_mapping
from .grpc_mapping import (
    GrpcTcpMapping,
    grpc_path_needs_ha_restore,
    mapping_allowed_by_capabilities,
    mapping_for_grpc_path,
    mappings_for_platform,
)
from .grpc_value_normalize import (
    coerce_bool,
    denormalize_for_exec,
    grpc_exec_unavailable_reason,
    ha_options_for_mapping,
    normalize_grpc_value,
    path_is_omit_zero_int,
)
from .helpers import (
    persist_notify_only_restore_state,
    restore_last_select_option,
    restore_last_switch_state,
    restore_notify_only_select,
    restore_notify_only_switch,
)
from .transport import GRPC_PATH_SW_STATUS, subwoofer_currently_linked

if TYPE_CHECKING:
    from homeassistant.config_entries import ConfigEntry

    from . import BraviaQuadConfigEntry
    from .bravia_grpc_client import BraviaGrpcClientAsync

_LOGGER = logging.getLogger(__name__)


def _coerce_bass_option(normalized: Any) -> str | None:
    """Map normalized bass (int 0-2 or min/mid/max) to select option."""
    if normalized is None:
        return None
    if isinstance(normalized, str) and normalized in BASS_LEVEL_OPTIONS:
        return normalized
    if isinstance(normalized, int):
        return BASS_LEVEL_VALUES_TO_OPTIONS.get(normalized)
    return None


async def _async_exec(
    grpc_client: BraviaGrpcClientAsync, spec: EntitySpec, ha_value: Any
) -> None:
    unavailable = grpc_exec_unavailable_reason(grpc_client.notify_state, spec.grpc_path)
    if unavailable is not None:
        raise HomeAssistantError(
            translation_domain=DOMAIN,
            translation_key="grpc_feature_unavailable",
            translation_placeholders={
                "path": spec.grpc_path,
                "reason": unavailable,
            },
        )

    kind, payload = denormalize_for_exec(spec.mapping, ha_value)
    ok = await grpc_client.async_exec_denormalized(spec.grpc_path, kind, payload)
    if not ok:
        raise HomeAssistantError(
            translation_domain=DOMAIN,
            translation_key="grpc_exec_failed",
            translation_placeholders={"path": spec.grpc_path},
        )


class BraviaGrpcMappedSwitch(BraviaGrpcPathMixin, RestoreEntity, SwitchEntity):
    """Bool gRPC path exposed as a switch."""

    _attr_entity_category = EntityCategory.CONFIG
    _attr_has_entity_name = True
    _attr_should_poll = False

    def __init__(
        self,
        grpc_client: BraviaGrpcClientAsync,
        entry: BraviaQuadConfigEntry,
        spec: EntitySpec,
    ) -> None:
        """Initialize gRPC mapped switch."""
        self._grpc_client = grpc_client
        self._spec = spec
        self._grpc_path = spec.grpc_path
        self._attr_translation_key = spec.translation_key
        self._attr_unique_id = entity_unique_id(entry, spec.unique_id_suffix)
        self._attr_device_info = get_device_info(entry)
        self._attr_entity_registry_enabled_default = spec.enabled_default
        raw = grpc_client.notify_state.get(spec.grpc_path)
        if raw is None:
            self._attr_is_on = None
        else:
            normalized = normalize_grpc_value(spec.mapping, raw)
            self._attr_is_on = coerce_bool(normalized)

    async def async_added_to_hass(self) -> None:
        """Restore state when added to Home Assistant."""
        await super().async_added_to_hass()
        if grpc_path_needs_ha_restore(self._grpc_path):
            await restore_notify_only_switch(self, self._grpc_client, self._grpc_path)
        elif self._attr_is_on is None:
            await restore_last_switch_state(self)
        self.async_write_ha_state()

    async def _on_grpc_state(self, value: Any) -> None:
        normalized = normalize_grpc_value(self._spec.mapping, value)
        coerced = coerce_bool(normalized)
        if coerced is None:
            return
        self._attr_is_on = coerced
        self.async_write_ha_state()

    def _sync_from_notify(self) -> None:
        """Apply notify_state to switch without optimistic exec assumptions."""
        raw = self._grpc_client.notify_state.get(self._spec.grpc_path)
        normalized = normalize_grpc_value(self._spec.mapping, raw)
        coerced = coerce_bool(normalized)
        if coerced is not None:
            self._attr_is_on = coerced

    async def async_turn_on(self, **_kwargs: Any) -> None:
        """Turn the switch on."""
        await _async_exec(self._grpc_client, self._spec, ha_value=True)
        self._sync_from_notify()
        self.async_write_ha_state()

    async def async_turn_off(self, **_kwargs: Any) -> None:
        """Turn the switch off."""
        await _async_exec(self._grpc_client, self._spec, ha_value=False)
        self._sync_from_notify()
        self.async_write_ha_state()

    async def async_will_remove_from_hass(self) -> None:
        """Persist restore state for notify-only paths."""
        await super().async_will_remove_from_hass()
        if grpc_path_needs_ha_restore(self._grpc_path):
            state = (
                "on"
                if self._attr_is_on
                else "off"
                if self._attr_is_on is False
                else None
            )
            persist_notify_only_restore_state(self, state)


_GRPC_BASS_PATH = "sound_setting.volume.bass"
_PLAYBACK_SELECT_PATHS = frozenset({"playback_control.function"})


class BraviaGrpcMappedSelect(BraviaGrpcPathMixin, RestoreEntity, SelectEntity):
    """Enum gRPC path exposed as a select."""

    _attr_has_entity_name = True
    _attr_should_poll = False

    def __init__(
        self,
        grpc_client: BraviaGrpcClientAsync,
        entry: BraviaQuadConfigEntry,
        spec: EntitySpec,
        *,
        options: list[str] | None = None,
    ) -> None:
        """Initialize gRPC mapped select."""
        self._grpc_client = grpc_client
        self._spec = spec
        self._grpc_path = spec.grpc_path
        self._attr_translation_key = spec.translation_key
        self._attr_unique_id = entity_unique_id(entry, spec.unique_id_suffix)
        self._attr_device_info = get_device_info(entry)
        self._attr_entity_registry_enabled_default = spec.enabled_default
        if spec.grpc_path not in _PLAYBACK_SELECT_PATHS:
            self._attr_entity_category = EntityCategory.CONFIG
        self._attr_options = options or ha_options_for_mapping(spec.mapping) or []
        normalized = normalize_grpc_value(
            spec.mapping, grpc_client.notify_state.get(spec.grpc_path)
        )
        option = str(normalized) if normalized is not None else None
        if option and option not in self._attr_options:
            self._attr_options = [*self._attr_options, option]
        self._attr_current_option = option if option in self._attr_options else None

    async def async_added_to_hass(self) -> None:
        """Restore state when added to Home Assistant."""
        await super().async_added_to_hass()
        if grpc_path_needs_ha_restore(self._grpc_path):
            await restore_notify_only_select(
                self,
                self._grpc_client,
                self._grpc_path,
                self._attr_options,
                mapping=self._spec.mapping,
            )
        elif self._attr_current_option is None:
            await restore_last_select_option(self, self._attr_options)
        self.async_write_ha_state()

    async def _on_grpc_state(self, value: Any) -> None:
        normalized = normalize_grpc_value(self._spec.mapping, value)
        if normalized is None:
            return
        option = str(normalized)
        if option not in self._attr_options:
            self._attr_options = [*self._attr_options, option]
        self._attr_current_option = option
        self.async_write_ha_state()

    async def async_select_option(self, option: str) -> None:
        """Change the selected option."""
        if option not in self._attr_options:
            raise HomeAssistantError(
                translation_domain=DOMAIN,
                translation_key="verify_unexpected_value",
                translation_placeholders={
                    "feature": self._grpc_path,
                    "actual": option,
                },
            )
        await _async_exec(self._grpc_client, self._spec, option)
        self._sync_select_from_notify()
        if grpc_path_needs_ha_restore(self._grpc_path):
            self._grpc_client.merge_notify_cache({self._grpc_path: option})
        self.async_write_ha_state()

    def _sync_select_from_notify(self) -> None:
        raw = self._grpc_client.notify_state.get(self._grpc_path)
        normalized = normalize_grpc_value(self._spec.mapping, raw)
        if normalized is None:
            return
        option = str(normalized)
        if option not in self._attr_options:
            self._attr_options = [*self._attr_options, option]
        self._attr_current_option = option

    async def async_will_remove_from_hass(self) -> None:
        """Persist restore state for notify-only paths."""
        await super().async_will_remove_from_hass()
        if grpc_path_needs_ha_restore(self._grpc_path):
            persist_notify_only_restore_state(self, self._attr_current_option)


class BraviaGrpcMappedNumber(BraviaGrpcPathMixin, NumberEntity):
    """Int gRPC path exposed as a number."""

    _attr_entity_category = EntityCategory.CONFIG
    _attr_has_entity_name = True
    _attr_mode = NumberMode.AUTO
    _attr_should_poll = False

    def __init__(
        self,
        grpc_client: BraviaGrpcClientAsync,
        entry: BraviaQuadConfigEntry,
        spec: EntitySpec,
        *,
        native_min_value: float,
        native_max_value: float,
    ) -> None:
        """Initialize gRPC mapped number."""
        self._grpc_client = grpc_client
        self._spec = spec
        self._grpc_path = spec.grpc_path
        self._attr_translation_key = spec.translation_key
        self._attr_unique_id = entity_unique_id(entry, spec.unique_id_suffix)
        self._attr_device_info = get_device_info(entry)
        self._attr_entity_registry_enabled_default = spec.enabled_default
        self._attr_native_min_value = native_min_value
        self._attr_native_max_value = native_max_value
        if spec.mapping.tcp_feature in (FEATURE_AV_SYNC, FEATURE_TV_AV_SYNC):
            self._attr_mode = NumberMode.SLIDER
            self._attr_native_step = AV_SYNC_STEP
            self._attr_native_unit_of_measurement = UnitOfTime.MILLISECONDS
        elif spec.mapping.tcp_feature == FEATURE_VOICE_ZOOM_LEVEL:
            self._attr_mode = NumberMode.SLIDER
            self._attr_native_step = 1
        raw = grpc_client.notify_state.get(spec.grpc_path)
        normalized = normalize_grpc_value(
            spec.mapping,
            raw,
            capability_index=grpc_client.capability_index,
        )
        try:
            self._attr_native_value = (
                float(normalized) if normalized is not None else None
            )
        except (TypeError, ValueError):
            self._attr_native_value = None

    async def async_added_to_hass(self) -> None:
        """Write initial state when added to Home Assistant."""
        await super().async_added_to_hass()
        self.async_write_ha_state()

    async def _on_grpc_state(self, value: Any) -> None:
        # Sibling int notifies often omit the value field (proto3). Blind
        # None→0 would wipe rear when subwoofer changes (and vice versa).
        if value is None and path_is_omit_zero_int(
            self._grpc_path, self._grpc_client.capability_index
        ):
            value = await self._grpc_client.async_get_states_single_path(
                self._grpc_path
            )

        normalized = normalize_grpc_value(
            self._spec.mapping,
            value,
            capability_index=self._grpc_client.capability_index,
        )
        try:
            native = float(normalized) if normalized is not None else None
        except (TypeError, ValueError):
            return
        # Reject out-of-range (catches any remaining unsigned wrap).
        if native is not None and (
            native < self._attr_native_min_value or native > self._attr_native_max_value
        ):
            return
        self._attr_native_value = native
        self.async_write_ha_state()

    async def async_set_native_value(self, value: float) -> None:
        """Set the number value."""
        int_value = int(value)
        await _async_exec(self._grpc_client, self._spec, int_value)
        self._sync_number_from_notify()
        self.async_write_ha_state()

    def _sync_number_from_notify(self) -> None:
        raw = self._grpc_client.notify_state.get(self._grpc_path)
        normalized = normalize_grpc_value(
            self._spec.mapping,
            raw,
            capability_index=self._grpc_client.capability_index,
        )
        try:
            self._attr_native_value = (
                float(normalized) if normalized is not None else None
            )
        except (TypeError, ValueError):
            return


class BraviaGrpcSubwooferNumber(BraviaGrpcMappedNumber):
    """Subwoofer level; unavailable while the wireless sub is not linked."""

    @property
    def available(self) -> bool:
        """Require gRPC session and a live subwoofer link."""
        if not super().available:
            return False
        return subwoofer_currently_linked(self._grpc_client.notify_state)

    def _grpc_state_callback(self, update: Any) -> None:
        """Refresh on level deltas and link status changes."""
        if update.path == GRPC_PATH_SW_STATUS:
            self.async_write_ha_state()
            return
        super()._grpc_state_callback(update)


class BraviaGrpcMappedSensor(BraviaGrpcPathMixin, SensorEntity):
    """Read-only gRPC path exposed as a sensor."""

    _attr_has_entity_name = True
    _attr_should_poll = False

    def __init__(
        self,
        grpc_client: BraviaGrpcClientAsync,
        entry: BraviaQuadConfigEntry,
        spec: EntitySpec,
        *,
        entity_category: EntityCategory | None = EntityCategory.DIAGNOSTIC,
        enabled_default: bool | None = None,
    ) -> None:
        """Initialize gRPC mapped sensor."""
        self._grpc_client = grpc_client
        self._spec = spec
        self._grpc_path = spec.grpc_path
        self._attr_translation_key = spec.translation_key
        self._attr_unique_id = entity_unique_id(entry, spec.unique_id_suffix)
        self._attr_device_info = get_device_info(entry)
        self._attr_entity_category = entity_category
        self._attr_entity_registry_enabled_default = (
            spec.enabled_default if enabled_default is None else enabled_default
        )
        normalized = normalize_grpc_value(
            spec.mapping, grpc_client.notify_state.get(spec.grpc_path)
        )
        self._attr_native_value = str(normalized) if normalized is not None else None

    async def _on_grpc_state(self, value: Any) -> None:
        normalized = normalize_grpc_value(self._spec.mapping, value)
        self._attr_native_value = str(normalized) if normalized is not None else None
        self.async_write_ha_state()


class BraviaGrpcBassLevelSelect(BraviaGrpcMappedSelect):
    """Bass level select (min/mid/max); unavailable while a wireless sub is linked."""

    def __init__(
        self,
        grpc_client: BraviaGrpcClientAsync,
        entry: BraviaQuadConfigEntry,
        spec: EntitySpec,
    ) -> None:
        """Initialize bass level select."""
        super().__init__(
            grpc_client,
            entry,
            spec,
            options=list(BASS_LEVEL_OPTIONS.keys()),
        )
        self._attr_unique_id = entity_unique_id(entry, "bass_level_select")
        self._attr_options = list(BASS_LEVEL_OPTIONS.keys())
        normalized = normalize_grpc_value(
            spec.mapping, grpc_client.notify_state.get(spec.grpc_path)
        )
        self._attr_current_option = _coerce_bass_option(normalized)

    @property
    def available(self) -> bool:
        """Require gRPC session and no live subwoofer link."""
        if not super().available:
            return False
        return not subwoofer_currently_linked(self._grpc_client.notify_state)

    def _grpc_state_callback(self, update: Any) -> None:
        """Refresh on bass deltas and link status changes."""
        if update.path == GRPC_PATH_SW_STATUS:
            self.async_write_ha_state()
            return
        super()._grpc_state_callback(update)

    async def _on_grpc_state(self, value: Any) -> None:
        normalized = normalize_grpc_value(self._spec.mapping, value)
        option = _coerce_bass_option(normalized)
        if option is None:
            return
        self._attr_current_option = option
        self.async_write_ha_state()

    def _sync_select_from_notify(self) -> None:
        option = _coerce_bass_option(
            normalize_grpc_value(
                self._spec.mapping,
                self._grpc_client.notify_state.get(self._grpc_path),
            )
        )
        if option is not None:
            self._attr_current_option = option


def _number_range(  # noqa: PLR0911
    mapping: GrpcTcpMapping,
    *,
    capability_index: dict[str, CapabilityMeta] | None = None,
) -> tuple[float, float]:
    cap_range = int_range_from_capability(mapping.grpc_path, capability_index)
    if cap_range is not None:
        return (float(cap_range[0]), float(cap_range[1]))
    if mapping.grpc_path == "sound_setting.volume.subwoofer":
        return (MIN_BASS_LEVEL, MAX_BASS_LEVEL)
    if mapping.tcp_feature == FEATURE_REAR_LEVEL:
        return (MIN_REAR_LEVEL, MAX_REAR_LEVEL)
    if mapping.tcp_feature == FEATURE_BASS_LEVEL:
        return (MIN_BASS_LEVEL, MAX_BASS_LEVEL)
    if mapping.tcp_feature == FEATURE_AV_SYNC:
        return (MIN_AV_SYNC, MAX_AV_SYNC)
    if mapping.tcp_feature == FEATURE_TV_AV_SYNC:
        return (MIN_AV_SYNC, MAX_AV_SYNC)
    if mapping.tcp_feature == FEATURE_VOICE_ZOOM_LEVEL:
        return (MIN_VOICE_ZOOM_LEVEL, MAX_VOICE_ZOOM_LEVEL)
    return (0, MAX_VOLUME)


def mapped_switch_entities(
    grpc_client: BraviaGrpcClientAsync, entry: ConfigEntry
) -> list[SwitchEntity]:
    """TCP-parity switch entities for gRPC mode."""
    caps = grpc_client.capability_paths
    entities: list[SwitchEntity] = []
    power = mapping_for_grpc_path("power")
    if power and mapping_allowed_by_capabilities(power.grpc_path, caps):
        entities.append(
            BraviaGrpcMappedSwitch(grpc_client, entry, entity_spec_for_mapping(power))
        )
    entities.extend(
        BraviaGrpcMappedSwitch(grpc_client, entry, entity_spec_for_mapping(mapping))
        for mapping in mappings_for_platform("switch", writable=True)
        if mapping_allowed_by_capabilities(mapping.grpc_path, caps)
    )
    return entities


def mapped_select_entities(
    grpc_client: BraviaGrpcClientAsync, entry: ConfigEntry
) -> list[SelectEntity]:
    """TCP-parity select entities for gRPC mode."""
    caps = grpc_client.capability_paths
    entities: list[SelectEntity] = []

    for mapping in mappings_for_platform("select", writable=True):
        if mapping.grpc_path == _GRPC_BASS_PATH:
            continue
        if not mapping_allowed_by_capabilities(mapping.grpc_path, caps):
            continue
        entities.append(
            BraviaGrpcMappedSelect(grpc_client, entry, entity_spec_for_mapping(mapping))
        )

    bass = mapping_for_grpc_path(_GRPC_BASS_PATH)
    if bass and mapping_allowed_by_capabilities(bass.grpc_path, caps):
        entities.append(
            BraviaGrpcBassLevelSelect(grpc_client, entry, entity_spec_for_mapping(bass))
        )
    return entities


def mapped_number_entities(
    grpc_client: BraviaGrpcClientAsync, entry: ConfigEntry
) -> list[NumberEntity]:
    """TCP-parity number entities for gRPC mode."""
    caps = grpc_client.capability_paths
    entities: list[NumberEntity] = []

    volume = mapping_for_grpc_path("volume")
    if volume and mapping_allowed_by_capabilities(volume.grpc_path, caps):
        spec = entity_spec_for_mapping(volume)
        entities.append(
            BraviaGrpcMappedNumber(
                grpc_client,
                entry,
                spec,
                native_min_value=0,
                native_max_value=MAX_VOLUME,
            )
        )

    for mapping in mappings_for_platform("number", writable=True):
        if mapping.grpc_path == _GRPC_BASS_PATH:
            continue
        if not mapping_allowed_by_capabilities(mapping.grpc_path, caps):
            continue
        if mapping.grpc_path == "sound_setting.volume.subwoofer":
            spec = entity_spec_for_mapping(mapping)
            lo, hi = _number_range(
                mapping, capability_index=grpc_client.capability_index
            )
            entities.append(
                BraviaGrpcSubwooferNumber(
                    grpc_client, entry, spec, native_min_value=lo, native_max_value=hi
                )
            )
            continue
        spec = entity_spec_for_mapping(mapping)
        lo, hi = _number_range(mapping, capability_index=grpc_client.capability_index)
        entities.append(
            BraviaGrpcMappedNumber(
                grpc_client, entry, spec, native_min_value=lo, native_max_value=hi
            )
        )
    entities.append(
        BraviaQuadVolumeStepIntervalNumber(entry, grpc_client, enabled_default=False)
    )
    return entities


def mapped_sensor_entities(
    grpc_client: BraviaGrpcClientAsync, entry: ConfigEntry
) -> list[SensorEntity]:
    """TCP-parity sensor entities for gRPC mode."""
    caps = grpc_client.capability_paths
    entities: list[SensorEntity] = []
    for mapping in mappings_for_platform("sensor", writable=False):
        if not mapping_allowed_by_capabilities(mapping.grpc_path, caps):
            continue
        spec = entity_spec_for_mapping(mapping)
        enabled = mapping.grpc_path != "system_setting.serial_number"
        entities.append(
            BraviaGrpcMappedSensor(grpc_client, entry, spec, enabled_default=enabled)
        )
    return entities
