"""Tests for gRPC media player now-playing metadata and transport controls."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from homeassistant.components.media_player import (
    MediaPlayerEntityFeature,
    MediaPlayerState,
    MediaType,
)

from custom_components.bravia_quad.grpc.client import NotifyStateUpdate
from custom_components.bravia_quad.grpc_media_player import (
    _BASE_SUPPORTED_FEATURES,
    _PATH_ALBUM,
    _PATH_ARTIST,
    _PATH_AUDIO_FORMAT,
    _PATH_AVAILABLE_VALUES,
    _PATH_COMMAND_AVAILABILITY,
    _PATH_COMMAND_UNAVAILABLE,
    _PATH_DURATION,
    _PATH_FUNCTION_UNAVAILABLE,
    _PATH_INPUT,
    _PATH_JACKET,
    _PATH_PLAYBACK_STATE,
    _PATH_POSITION,
    _PATH_SERVICE_NAME,
    _PATH_SOUND_EFFECT,
    _PATH_SPOTIFY_PLAYLIST,
    _PATH_TITLE,
    _POSITION_WRITE_INTERVAL,
    _TRANSPORT_FEATURE_BY_ACTION,
    BraviaGrpcMediaPlayer,
    _parse_available_values,
)


def _mock_create_task(coro: object) -> MagicMock:
    if asyncio.iscoroutine(coro):
        coro.close()
    return MagicMock()


def _base_notify_state() -> dict[str, object]:
    return {
        "power": "on",
        "mute": "off",
        "volume": 50,
        "playback_control.function": "spotify",
        "playback_control.playback_state": "play",
    }


@pytest.fixture
def grpc_client() -> MagicMock:
    client = MagicMock()
    client.is_connected = True
    client.notify_state = _base_notify_state()
    client.async_exec_command = AsyncMock(return_value=True)
    client.async_exec_denormalized = AsyncMock(return_value=True)
    client.async_fetch_field_paths = AsyncMock(return_value=0)
    client.add_state_callback = MagicMock()
    client.remove_state_callback = MagicMock()
    client.volume_step_interval = 0
    return client


@pytest.fixture
def entry() -> MagicMock:
    entry = MagicMock()
    entry.unique_id = "serial123"
    entry.data = {}
    return entry


def test_playback_seed_from_cache_airplay_source(
    grpc_client: MagicMock, entry: MagicMock
) -> None:
    grpc_client.notify_state.update(
        {
            _PATH_INPUT: "airplay",
            _PATH_TITLE: "Harmony in the Distance",
            _PATH_ARTIST: "M-High",
            _PATH_ALBUM: "DJ-Kicks: Disclosure",
            _PATH_DURATION: 421,
            _PATH_POSITION: 247,
            _PATH_SERVICE_NAME: "AirPlay",
            _PATH_PLAYBACK_STATE: "play",
        }
    )
    entity = BraviaGrpcMediaPlayer(grpc_client, entry)

    assert entity._attr_source == "airplay2"
    assert entity._attr_state == MediaPlayerState.PLAYING
    assert entity._attr_media_title == "Harmony in the Distance"
    assert entity._attr_app_name == "AirPlay"


def test_playback_seed_without_title_uses_playback_state(
    grpc_client: MagicMock, entry: MagicMock
) -> None:
    grpc_client.notify_state.update(
        {
            _PATH_INPUT: "airplay2",
            _PATH_PLAYBACK_STATE: "play",
            _PATH_SERVICE_NAME: "AirPlay",
            _PATH_POSITION: 10,
        }
    )
    entity = BraviaGrpcMediaPlayer(grpc_client, entry)

    assert entity._attr_state == MediaPlayerState.PLAYING
    assert entity._attr_media_position == 10
    assert entity._attr_app_name == "AirPlay"
    assert entity._attr_media_title is None


def test_airplay2_excluded_from_source_list_when_inactive(
    grpc_client: MagicMock, entry: MagicMock
) -> None:
    grpc_client.notify_state[_PATH_INPUT] = "tv"
    entity = BraviaGrpcMediaPlayer(grpc_client, entry)

    assert "airplay2" not in entity._attr_source_list


def test_airplay2_in_source_list_when_active(
    grpc_client: MagicMock, entry: MagicMock
) -> None:
    grpc_client.notify_state[_PATH_INPUT] = "airplay"
    entity = BraviaGrpcMediaPlayer(grpc_client, entry)

    assert entity._attr_source == "airplay2"
    assert "airplay2" in entity._attr_source_list


def test_supported_features_include_transport_on_airplay2(
    grpc_client: MagicMock, entry: MagicMock
) -> None:
    grpc_client.notify_state.update(
        {
            _PATH_INPUT: "airplay2",
            _PATH_COMMAND_AVAILABILITY: True,
        }
    )
    entity = BraviaGrpcMediaPlayer(grpc_client, entry)

    assert entity.supported_features == (
        _BASE_SUPPORTED_FEATURES | _transport_features()
    )


@pytest.mark.asyncio
async def test_async_select_source_airplay2_noop_when_inactive(
    grpc_client: MagicMock, entry: MagicMock
) -> None:
    grpc_client.notify_state[_PATH_INPUT] = "tv"
    entity = BraviaGrpcMediaPlayer(grpc_client, entry)

    await entity.async_select_source("airplay2")

    grpc_client.async_exec_command.assert_not_awaited()


def test_parse_available_values_normalizes_airplay() -> None:
    assert _parse_available_values("tv, airplay, spotify") == [
        "tv",
        "airplay2",
        "spotify",
    ]


def test_playback_seed_from_cache(grpc_client: MagicMock, entry: MagicMock) -> None:
    grpc_client.notify_state.update(
        {
            _PATH_TITLE: "Keep Moving",
            _PATH_ARTIST: "Rafael Cerato",
            _PATH_ALBUM: "Keep Moving",
            _PATH_DURATION: 209,
            _PATH_POSITION: 29,
            _PATH_JACKET: "https://example.com/cover.jpg",
            _PATH_SPOTIFY_PLAYLIST: "Hey Bro",
            _PATH_SERVICE_NAME: "Spotify",
        }
    )
    entity = BraviaGrpcMediaPlayer(grpc_client, entry)

    assert entity._attr_state == MediaPlayerState.PLAYING
    assert entity._attr_media_title == "Keep Moving"
    assert entity._attr_media_artist == "Rafael Cerato"
    assert entity._attr_media_album_name == "Keep Moving"
    assert entity._attr_media_content_type == MediaType.MUSIC
    assert entity._attr_media_duration == 209
    assert entity._attr_media_position == 29
    assert entity._attr_media_image_url == "https://example.com/cover.jpg"
    assert entity._attr_media_playlist == "Hey Bro"
    assert entity._attr_app_name == "Spotify"
    assert entity._attr_media_image_remotely_accessible is True


def test_playback_seed_skipped_for_tv_source(
    grpc_client: MagicMock, entry: MagicMock
) -> None:
    grpc_client.notify_state[_PATH_INPUT] = "tv"
    grpc_client.notify_state[_PATH_TITLE] = "Keep Moving"
    entity = BraviaGrpcMediaPlayer(grpc_client, entry)

    assert entity._attr_media_title is None


def test_duration_negative_treated_as_unknown(
    grpc_client: MagicMock, entry: MagicMock
) -> None:
    grpc_client.notify_state.update(
        {
            _PATH_TITLE: "Live stream",
            _PATH_DURATION: -1,
        }
    )
    entity = BraviaGrpcMediaPlayer(grpc_client, entry)

    assert entity._attr_media_duration is None


@pytest.mark.asyncio
async def test_playback_title_notify_updates_state(
    grpc_client: MagicMock, entry: MagicMock
) -> None:
    entity = BraviaGrpcMediaPlayer(grpc_client, entry)
    entity.hass = MagicMock()
    entity.async_write_ha_state = MagicMock()

    await entity._on_playback_update(_PATH_TITLE, "New Track")

    assert entity._attr_media_title == "New Track"
    assert entity._attr_media_content_type == MediaType.MUSIC
    assert entity._attr_state == MediaPlayerState.PLAYING
    entity.async_write_ha_state.assert_called_once()


@pytest.mark.asyncio
async def test_playback_state_pause(grpc_client: MagicMock, entry: MagicMock) -> None:
    grpc_client.notify_state[_PATH_TITLE] = "Keep Moving"
    grpc_client.notify_state[_PATH_PLAYBACK_STATE] = "pause"
    entity = BraviaGrpcMediaPlayer(grpc_client, entry)
    entity.hass = MagicMock()
    entity.async_write_ha_state = MagicMock()

    await entity._on_playback_update(_PATH_PLAYBACK_STATE, "pause")

    assert entity._attr_state == MediaPlayerState.PAUSED


@pytest.mark.asyncio
async def test_playback_title_cleared_clears_metadata(
    grpc_client: MagicMock, entry: MagicMock
) -> None:
    grpc_client.notify_state.update(
        {
            _PATH_TITLE: "Keep Moving",
            _PATH_ARTIST: "Rafael Cerato",
        }
    )
    entity = BraviaGrpcMediaPlayer(grpc_client, entry)
    entity.hass = MagicMock()
    entity.async_write_ha_state = MagicMock()

    await entity._on_playback_update(_PATH_TITLE, "")

    assert entity._attr_media_title is None
    assert entity._attr_media_artist is None
    assert entity._attr_media_content_type is None
    entity.async_write_ha_state.assert_called_once()


@pytest.mark.asyncio
async def test_input_change_away_from_streaming_clears_metadata(
    grpc_client: MagicMock, entry: MagicMock
) -> None:
    grpc_client.notify_state[_PATH_TITLE] = "Keep Moving"
    entity = BraviaGrpcMediaPlayer(grpc_client, entry)
    entity.hass = MagicMock()
    entity.async_write_ha_state = MagicMock()

    await entity._on_path_update(_PATH_INPUT, "tv")

    assert entity._attr_source == "tv"
    assert entity._attr_media_title is None


@pytest.mark.asyncio
async def test_position_notify_throttles_writes(
    grpc_client: MagicMock, entry: MagicMock
) -> None:
    grpc_client.notify_state[_PATH_TITLE] = "Keep Moving"
    entity = BraviaGrpcMediaPlayer(grpc_client, entry)
    entity.hass = MagicMock()
    entity.async_write_ha_state = MagicMock()
    entity._last_position_write = 1000.0
    entity.hass.async_create_task = _mock_create_task

    with patch(
        "custom_components.bravia_quad.grpc_media_player.time.monotonic",
        return_value=1001.0,
    ):
        await entity._on_playback_update(_PATH_POSITION, 30)

    assert entity._attr_media_position == 30
    entity.async_write_ha_state.assert_not_called()
    assert entity._position_write_task is not None


@pytest.mark.asyncio
async def test_position_notify_writes_after_interval(
    grpc_client: MagicMock, entry: MagicMock
) -> None:
    grpc_client.notify_state[_PATH_TITLE] = "Keep Moving"
    entity = BraviaGrpcMediaPlayer(grpc_client, entry)
    entity.hass = MagicMock()
    entity.async_write_ha_state = MagicMock()
    entity._last_position_write = 1000.0

    with patch(
        "custom_components.bravia_quad.grpc_media_player.time.monotonic",
        return_value=1000.0 + _POSITION_WRITE_INTERVAL,
    ):
        await entity._on_playback_update(_PATH_POSITION, 31)

    assert entity._attr_media_position == 31
    entity.async_write_ha_state.assert_called_once()


def _transport_features() -> MediaPlayerEntityFeature:
    features = MediaPlayerEntityFeature(0)
    for action in _TRANSPORT_FEATURE_BY_ACTION:
        features |= _TRANSPORT_FEATURE_BY_ACTION[action]
    return features


def test_supported_features_include_transport_on_spotify(
    grpc_client: MagicMock, entry: MagicMock
) -> None:
    entity = BraviaGrpcMediaPlayer(grpc_client, entry)

    assert entity.supported_features == (
        _BASE_SUPPORTED_FEATURES | _transport_features()
    )


def test_supported_features_exclude_transport_on_tv(
    grpc_client: MagicMock, entry: MagicMock
) -> None:
    grpc_client.notify_state[_PATH_INPUT] = "tv"
    entity = BraviaGrpcMediaPlayer(grpc_client, entry)

    assert entity.supported_features == _BASE_SUPPORTED_FEATURES


def test_supported_features_exclude_transport_when_power_off(
    grpc_client: MagicMock, entry: MagicMock
) -> None:
    grpc_client.notify_state["power"] = "off"
    entity = BraviaGrpcMediaPlayer(grpc_client, entry)

    assert entity.supported_features == _BASE_SUPPORTED_FEATURES


def test_supported_features_respect_command_availability(
    grpc_client: MagicMock, entry: MagicMock
) -> None:
    grpc_client.notify_state[_PATH_COMMAND_AVAILABILITY] = "play pause next prev"
    entity = BraviaGrpcMediaPlayer(grpc_client, entry)

    assert entity.supported_features & MediaPlayerEntityFeature.PLAY
    assert entity.supported_features & MediaPlayerEntityFeature.PAUSE
    assert entity.supported_features & MediaPlayerEntityFeature.NEXT_TRACK
    assert entity.supported_features & MediaPlayerEntityFeature.PREVIOUS_TRACK


def test_supported_features_string_availability_maps_next_track(
    grpc_client: MagicMock, entry: MagicMock
) -> None:
    grpc_client.notify_state[_PATH_COMMAND_AVAILABILITY] = "play pause next"
    entity = BraviaGrpcMediaPlayer(grpc_client, entry)

    assert entity.supported_features & MediaPlayerEntityFeature.NEXT_TRACK


def test_supported_features_string_availability_maps_previous_track(
    grpc_client: MagicMock, entry: MagicMock
) -> None:
    grpc_client.notify_state[_PATH_COMMAND_AVAILABILITY] = "play pause next prev"
    entity = BraviaGrpcMediaPlayer(grpc_client, entry)

    assert entity.supported_features & MediaPlayerEntityFeature.PREVIOUS_TRACK


def test_supported_features_int_availability_true(
    grpc_client: MagicMock, entry: MagicMock
) -> None:
    grpc_client.notify_state[_PATH_COMMAND_AVAILABILITY] = 1
    entity = BraviaGrpcMediaPlayer(grpc_client, entry)

    assert entity.supported_features == (
        _BASE_SUPPORTED_FEATURES | _transport_features()
    )


def test_airplay2_hides_transport_without_availability(
    grpc_client: MagicMock, entry: MagicMock
) -> None:
    grpc_client.notify_state.update(
        {
            _PATH_INPUT: "airplay",
            _PATH_COMMAND_AVAILABILITY: None,
        }
    )
    entity = BraviaGrpcMediaPlayer(grpc_client, entry)

    assert entity._attr_source == "airplay2"
    assert entity.supported_features == _BASE_SUPPORTED_FEATURES


def test_supported_features_bool_command_availability_true(
    grpc_client: MagicMock, entry: MagicMock
) -> None:
    grpc_client.notify_state[_PATH_COMMAND_AVAILABILITY] = True
    entity = BraviaGrpcMediaPlayer(grpc_client, entry)

    assert entity.supported_features == (
        _BASE_SUPPORTED_FEATURES | _transport_features()
    )


def test_supported_features_bool_command_availability_false(
    grpc_client: MagicMock, entry: MagicMock
) -> None:
    grpc_client.notify_state[_PATH_COMMAND_AVAILABILITY] = False
    entity = BraviaGrpcMediaPlayer(grpc_client, entry)

    assert entity.supported_features == _BASE_SUPPORTED_FEATURES


def test_supported_features_include_transport_when_availability_false_reason_none(
    grpc_client: MagicMock, entry: MagicMock
) -> None:
    grpc_client.notify_state.update(
        {
            _PATH_COMMAND_AVAILABILITY: False,
            _PATH_COMMAND_UNAVAILABLE: "none",
        }
    )
    entity = BraviaGrpcMediaPlayer(grpc_client, entry)

    assert entity.supported_features == (
        _BASE_SUPPORTED_FEATURES | _transport_features()
    )


def test_bluetooth_keeps_transport_when_availability_false_reason_none(
    grpc_client: MagicMock, entry: MagicMock
) -> None:
    grpc_client.notify_state.update(
        {
            _PATH_INPUT: "bluetooth",
            _PATH_COMMAND_AVAILABILITY: False,
            _PATH_COMMAND_UNAVAILABLE: "none",
        }
    )
    entity = BraviaGrpcMediaPlayer(grpc_client, entry)

    assert entity._attr_source == "bluetooth"
    assert entity.supported_features == (
        _BASE_SUPPORTED_FEATURES | _transport_features()
    )


def test_airplay2_hides_transport_when_availability_false_reason_none(
    grpc_client: MagicMock, entry: MagicMock
) -> None:
    grpc_client.notify_state.update(
        {
            _PATH_INPUT: "airplay",
            _PATH_COMMAND_AVAILABILITY: False,
            _PATH_COMMAND_UNAVAILABLE: "none",
        }
    )
    entity = BraviaGrpcMediaPlayer(grpc_client, entry)

    assert entity._attr_source == "airplay2"
    assert entity.supported_features == _BASE_SUPPORTED_FEATURES


@pytest.mark.asyncio
async def test_async_media_play_exec(grpc_client: MagicMock, entry: MagicMock) -> None:
    entity = BraviaGrpcMediaPlayer(grpc_client, entry)

    await entity.async_media_play()

    grpc_client.async_exec_denormalized.assert_awaited_once_with(
        "playback_control.playback_command",
        "string_value",
        "play",
    )


@pytest.mark.asyncio
async def test_async_media_pause_exec(grpc_client: MagicMock, entry: MagicMock) -> None:
    grpc_client.async_fetch_field_paths = AsyncMock(return_value=0)
    entity = BraviaGrpcMediaPlayer(grpc_client, entry)

    await entity.async_media_pause()

    grpc_client.async_exec_denormalized.assert_awaited_once_with(
        "playback_control.playback_command",
        "string_value",
        "pause",
    )


@pytest.mark.asyncio
async def test_async_media_next_track_exec(
    grpc_client: MagicMock, entry: MagicMock
) -> None:
    entity = BraviaGrpcMediaPlayer(grpc_client, entry)

    await entity.async_media_next_track()

    grpc_client.async_exec_denormalized.assert_awaited_once_with(
        "playback_control.playback_command",
        "string_value",
        "next",
    )


@pytest.mark.asyncio
async def test_async_media_previous_track_exec(
    grpc_client: MagicMock, entry: MagicMock
) -> None:
    entity = BraviaGrpcMediaPlayer(grpc_client, entry)

    await entity.async_media_previous_track()

    grpc_client.async_exec_denormalized.assert_awaited_once_with(
        "playback_control.playback_command",
        "string_value",
        "prev",
    )


@pytest.mark.asyncio
async def test_async_media_play_skipped_on_tv_source(
    grpc_client: MagicMock, entry: MagicMock
) -> None:
    grpc_client.notify_state[_PATH_INPUT] = "tv"
    entity = BraviaGrpcMediaPlayer(grpc_client, entry)

    await entity.async_media_play()

    grpc_client.async_exec_command.assert_not_awaited()


@pytest.mark.asyncio
async def test_command_availability_notify_refreshes_state(
    grpc_client: MagicMock, entry: MagicMock
) -> None:
    grpc_client.async_fetch_field_paths = AsyncMock(return_value=0)
    entity = BraviaGrpcMediaPlayer(grpc_client, entry)
    entity.hass = MagicMock()
    entity.async_write_ha_state = MagicMock()

    await entity._on_command_availability_update()

    entity.async_write_ha_state.assert_called_once()


def test_grpc_state_callback_routes_command_availability(
    grpc_client: MagicMock, entry: MagicMock
) -> None:
    entity = BraviaGrpcMediaPlayer(grpc_client, entry)
    entity.hass = MagicMock()
    entity.hass.async_create_task = MagicMock(side_effect=_mock_create_task)

    entity._grpc_state_callback(
        NotifyStateUpdate(path=_PATH_COMMAND_AVAILABILITY, value="play pause next")
    )

    entity.hass.async_create_task.assert_called_once()


def test_grpc_state_callback_routes_playback_paths(
    grpc_client: MagicMock, entry: MagicMock
) -> None:
    entity = BraviaGrpcMediaPlayer(grpc_client, entry)
    entity.hass = MagicMock()
    entity.hass.async_create_task = MagicMock(side_effect=_mock_create_task)

    entity._grpc_state_callback(NotifyStateUpdate(path=_PATH_ARTIST, value="Artist"))

    entity.hass.async_create_task.assert_called_once()


def test_metadata_seed_from_cache(grpc_client: MagicMock, entry: MagicMock) -> None:
    grpc_client.notify_state.update(
        {
            _PATH_INPUT: "tv",
            _PATH_AUDIO_FORMAT: "Dolby Atmos",
            _PATH_FUNCTION_UNAVAILABLE: "none",
        }
    )
    entity = BraviaGrpcMediaPlayer(grpc_client, entry)

    assert entity.extra_state_attributes["audio_format"] == "Dolby Atmos"
    assert "bt_codec" not in entity.extra_state_attributes


def test_metadata_filtered_by_source(grpc_client: MagicMock, entry: MagicMock) -> None:
    grpc_client.notify_state.update(
        {
            _PATH_INPUT: "bluetooth",
            "playback_control.bt_codec": "LDAC",
            _PATH_AUDIO_FORMAT: "PCM",
        }
    )
    entity = BraviaGrpcMediaPlayer(grpc_client, entry)

    assert entity.extra_state_attributes["bt_codec"] == "LDAC"
    assert "audio_format" not in entity.extra_state_attributes


def test_parse_available_values_comma_separated() -> None:
    assert _parse_available_values("tv, spotify, bluetooth") == [
        "tv",
        "spotify",
        "bluetooth",
    ]


def test_dynamic_source_list_from_notify(
    grpc_client: MagicMock, entry: MagicMock
) -> None:
    grpc_client.notify_state[_PATH_AVAILABLE_VALUES] = "tv,hdmi1,spotify"
    entity = BraviaGrpcMediaPlayer(grpc_client, entry)

    assert entity._attr_source_list == ["tv", "hdmi1", "spotify"]


def test_supported_features_include_sound_mode(
    grpc_client: MagicMock, entry: MagicMock
) -> None:
    entity = BraviaGrpcMediaPlayer(grpc_client, entry)

    assert entity.supported_features & MediaPlayerEntityFeature.SELECT_SOUND_MODE


def test_supported_features_hide_source_when_unavailable(
    grpc_client: MagicMock, entry: MagicMock
) -> None:
    grpc_client.notify_state[_PATH_FUNCTION_UNAVAILABLE] = "unsupported_input"
    entity = BraviaGrpcMediaPlayer(grpc_client, entry)

    assert not entity.supported_features & MediaPlayerEntityFeature.SELECT_SOURCE


@pytest.mark.asyncio
async def test_async_added_to_hass_backfills_playback_paths(
    grpc_client: MagicMock, entry: MagicMock
) -> None:
    grpc_client.async_fetch_field_paths = AsyncMock(return_value=3)
    entity = BraviaGrpcMediaPlayer(grpc_client, entry)
    entity.hass = MagicMock()
    entity.async_write_ha_state = MagicMock()

    await entity.async_added_to_hass()

    grpc_client.async_fetch_field_paths.assert_awaited_once()
    paths = grpc_client.async_fetch_field_paths.await_args.args[0]
    assert _PATH_COMMAND_AVAILABILITY in paths


@pytest.mark.asyncio
async def test_async_select_sound_mode_exec(
    grpc_client: MagicMock, entry: MagicMock
) -> None:
    entity = BraviaGrpcMediaPlayer(grpc_client, entry)
    entity.hass = MagicMock()
    entity.async_write_ha_state = MagicMock()

    await entity.async_select_sound_mode("neural_x")

    grpc_client.async_exec_command.assert_awaited_once_with(
        _PATH_SOUND_EFFECT,
        string_value="Neural:X",
    )
    assert entity._attr_sound_mode == "neural_x"
