"""Tests for the Bravia HTTP client."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import aiohttp
import pytest

from custom_components.bravia_quad.bravia_http_client import (
    BraviaHttpClient,
    DeviceDetails,
    FirmwareUpdateStatus,
    LatestFirmwareInfo,
    SystemInfo,
)


@pytest.fixture
def mock_session() -> MagicMock:
    """Return a mocked aiohttp ClientSession."""
    return MagicMock(spec=aiohttp.ClientSession)


@pytest.fixture
def http_client(mock_session: MagicMock) -> BraviaHttpClient:
    """Return an HTTP client with a mocked session."""
    return BraviaHttpClient("192.168.1.100", mock_session)


def _mock_post_response(data: dict) -> MagicMock:
    """Create a mock POST response context manager."""
    response = AsyncMock()
    response.raise_for_status = MagicMock()
    response.json = AsyncMock(return_value=data)

    ctx = AsyncMock()
    ctx.__aenter__ = AsyncMock(return_value=response)
    ctx.__aexit__ = AsyncMock(return_value=False)
    return ctx


def _mock_get_response(text: str) -> MagicMock:
    """Create a mock GET response context manager."""
    response = AsyncMock()
    response.raise_for_status = MagicMock()
    response.text = AsyncMock(return_value=text)

    ctx = AsyncMock()
    ctx.__aenter__ = AsyncMock(return_value=response)
    ctx.__aexit__ = AsyncMock(return_value=False)
    return ctx


async def test_get_system_info(
    http_client: BraviaHttpClient,
    mock_session: MagicMock,
) -> None:
    """Test fetching system info."""
    mock_session.post.return_value = _mock_post_response(
        {
            "type": "http_get_result",
            "packet": [
                [
                    {"feature": "system.version", "value": "001.100"},
                    {"feature": "system.modelname", "value": "BRAVIA Theatre Quad"},
                ]
            ],
        }
    )

    info = await http_client.async_get_system_info()

    assert info.version == "001.100"
    assert info.model_name == "BRAVIA Theatre Quad"


async def test_get_system_info_connection_error(
    http_client: BraviaHttpClient,
    mock_session: MagicMock,
) -> None:
    """Test system info when connection fails."""
    mock_session.post.return_value = _mock_post_response({})
    mock_session.post.side_effect = aiohttp.ClientError()

    info = await http_client.async_get_system_info()

    assert info == SystemInfo()


async def test_probe_reachable_success(http_client: BraviaHttpClient) -> None:
    """Probe sets reachable when the management port accepts a connection."""
    writer = MagicMock()
    writer.wait_closed = AsyncMock()
    with patch(
        "custom_components.bravia_quad.bravia_http_client.asyncio.open_connection",
        new=AsyncMock(return_value=(MagicMock(), writer)),
    ):
        assert await http_client.async_probe_reachable() is True
    assert http_client.reachable is True
    writer.close.assert_called_once()


async def test_probe_reachable_connection_refused(
    http_client: BraviaHttpClient,
) -> None:
    """Probe clears reachable when nothing listens on :54545."""
    with patch(
        "custom_components.bravia_quad.bravia_http_client.asyncio.open_connection",
        new=AsyncMock(side_effect=ConnectionRefusedError()),
    ):
        assert await http_client.async_probe_reachable() is False
    assert http_client.reachable is False


async def test_get_device_details(
    http_client: BraviaHttpClient,
    mock_session: MagicMock,
) -> None:
    """Test fetching device details."""
    mock_session.post.return_value = _mock_post_response(
        {
            "type": "http_get_result",
            "packet": [
                [
                    {"feature": "network.devicename", "value": "Living Room"},
                    {"feature": "network.connectiontype", "value": "wired"},
                    {"feature": "network.internet", "value": "connected"},
                    {
                        "feature": "network.macaddress_wired",
                        "value": "aa:bb:cc:dd:ee:ff",
                    },
                    {
                        "feature": "network.macaddress_wireless",
                        "value": "11:22:33:44:55:66",
                    },
                ],
                [{"feature": "inet4.ipaddress", "value": "192.168.1.100"}],
                [{"feature": "inet6.ipaddress", "value": "fe80::1"}],
                [{"feature": "wlan.strength", "value": "ERR"}],
            ],
        }
    )

    details = await http_client.async_get_device_details()

    assert details.device_name == "Living Room"
    assert details.connection_type == "wired"
    assert details.internet == "connected"
    assert details.ipv4_address == "192.168.1.100"
    assert details.ipv6_address == "fe80::1"
    assert details.wifi_signal is None  # ERR filtered out
    assert details.mac_wired == "aa:bb:cc:dd:ee:ff"
    assert details.mac_wireless == "11:22:33:44:55:66"


async def test_get_device_details_connection_error(
    http_client: BraviaHttpClient,
    mock_session: MagicMock,
) -> None:
    """Test device details when connection fails."""
    mock_session.post.side_effect = aiohttp.ClientError()

    details = await http_client.async_get_device_details()

    assert details == DeviceDetails()


async def test_get_device_details_nak_filtered(
    http_client: BraviaHttpClient,
    mock_session: MagicMock,
) -> None:
    """Test that NAK values are filtered to None."""
    mock_session.post.return_value = _mock_post_response(
        {
            "type": "http_get_result",
            "packet": [
                [
                    {"feature": "network.devicename", "value": "NAK"},
                    {"feature": "network.connectiontype", "value": "wired"},
                    {"feature": "network.internet", "value": "ERR"},
                    {
                        "feature": "network.macaddress_wired",
                        "value": "aa:bb:cc:dd:ee:ff",
                    },
                    {"feature": "network.macaddress_wireless", "value": "NAK"},
                ],
                [{"feature": "inet4.ipaddress", "value": "192.168.1.100"}],
                [{"feature": "inet6.ipaddress", "value": "ERR"}],
                [{"feature": "wlan.strength", "value": "NAK"}],
            ],
        }
    )

    details = await http_client.async_get_device_details()

    assert details.device_name is None
    assert details.connection_type == "wired"
    assert details.internet is None
    assert details.ipv6_address is None
    assert details.wifi_signal is None
    assert details.mac_wireless is None


async def test_check_firmware_update_available(
    http_client: BraviaHttpClient,
    mock_session: MagicMock,
) -> None:
    """Test firmware update available."""
    mock_session.post.return_value = _mock_post_response(
        {
            "type": "http_get_result",
            "packet": [[{"feature": "fw.check_update", "value": "ok"}]],
        }
    )

    status = await http_client.async_check_firmware_update()

    assert status is FirmwareUpdateStatus.UPDATE_AVAILABLE


async def test_check_firmware_up_to_date(
    http_client: BraviaHttpClient,
    mock_session: MagicMock,
) -> None:
    """Test firmware up to date."""
    mock_session.post.return_value = _mock_post_response(
        {
            "type": "http_get_result",
            "packet": [[{"feature": "fw.check_update", "value": "ng"}]],
        }
    )

    status = await http_client.async_check_firmware_update()

    assert status is FirmwareUpdateStatus.UP_TO_DATE


async def test_check_firmware_connection_error(
    http_client: BraviaHttpClient,
    mock_session: MagicMock,
) -> None:
    """Test firmware check when connection fails."""
    mock_session.post.side_effect = TimeoutError()

    status = await http_client.async_check_firmware_update()

    assert status is FirmwareUpdateStatus.ERROR


async def test_check_firmware_unexpected_response(
    http_client: BraviaHttpClient,
    mock_session: MagicMock,
) -> None:
    """Test firmware check with unexpected response type."""
    mock_session.post.return_value = _mock_post_response(
        {
            "type": "some_other_type",
            "packet": [],
        }
    )

    status = await http_client.async_check_firmware_update()

    assert status is FirmwareUpdateStatus.ERROR


async def test_request_firmware_update_success(
    http_client: BraviaHttpClient,
    mock_session: MagicMock,
) -> None:
    """Test triggering firmware update."""
    mock_session.post.return_value = _mock_post_response(
        {
            "type": "http_set_result",
            "packet": [{"value": "ACK"}],
        }
    )

    result = await http_client.async_request_firmware_update()

    assert result is True


async def test_request_firmware_update_rejected(
    http_client: BraviaHttpClient,
    mock_session: MagicMock,
) -> None:
    """Test firmware update request rejected by device."""
    mock_session.post.return_value = _mock_post_response(
        {
            "type": "http_set_result",
            "packet": [{"value": "NAK"}],
        }
    )

    result = await http_client.async_request_firmware_update()

    assert result is False


async def test_request_firmware_update_connection_error(
    http_client: BraviaHttpClient,
    mock_session: MagicMock,
) -> None:
    """Test firmware update when connection fails."""
    mock_session.post.side_effect = aiohttp.ClientError()

    result = await http_client.async_request_firmware_update()

    assert result is False


async def test_get_latest_firmware_info(
    http_client: BraviaHttpClient,
    mock_session: MagicMock,
) -> None:
    """Test fetching latest firmware info from Sony."""
    xml_text = (
        "eaid=XXXXXX\ndaid=YYYYYY\ndigest=abc123\n"
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        "<UpdateInfo>"
        '<Distribution Version="001.200" />'
        "</UpdateInfo>"
    )
    mock_session.get.return_value = _mock_get_response(xml_text)

    info = await http_client.async_get_latest_firmware_info("BRAVIA Theatre Quad")

    assert info.version == "001.200"
    assert (
        info.release_url
        == "https://www.sony.co.uk/electronics/support/software/00342249"
    )


async def test_get_latest_firmware_info_unknown_model(
    http_client: BraviaHttpClient,
    mock_session: MagicMock,
) -> None:
    """Test firmware info for unknown model returns empty."""
    info = await http_client.async_get_latest_firmware_info("Unknown Model")

    assert info == LatestFirmwareInfo()
    mock_session.get.assert_not_called()


async def test_get_latest_firmware_info_none_model(
    http_client: BraviaHttpClient,
    mock_session: MagicMock,
) -> None:
    """Test firmware info with None model returns empty."""
    info = await http_client.async_get_latest_firmware_info(None)

    assert info == LatestFirmwareInfo()


async def test_get_latest_firmware_info_connection_error(
    http_client: BraviaHttpClient,
    mock_session: MagicMock,
) -> None:
    """Test firmware info when Sony server unreachable."""
    mock_session.get.side_effect = aiohttp.ClientError()

    info = await http_client.async_get_latest_firmware_info("BRAVIA Theatre Quad")

    assert info == LatestFirmwareInfo()


async def test_parse_update_info_xml_no_xml() -> None:
    """Test parsing response with no XML content."""
    info = BraviaHttpClient._parse_update_info_xml("not xml at all")

    assert info == LatestFirmwareInfo()


async def test_parse_update_info_xml_no_distribution() -> None:
    """Test parsing XML without Distribution element."""
    xml = '<?xml version="1.0"?><UpdateInfo></UpdateInfo>'
    info = BraviaHttpClient._parse_update_info_xml(xml)

    assert info == LatestFirmwareInfo()


async def test_parse_update_info_xml_no_version_attribute() -> None:
    """Test parsing XML with Distribution but no Version."""
    xml = '<?xml version="1.0"?><UpdateInfo><Distribution /></UpdateInfo>'
    info = BraviaHttpClient._parse_update_info_xml(xml)

    assert info == LatestFirmwareInfo()


async def test_device_details_cache_prevents_redundant_calls(
    http_client: BraviaHttpClient,
    mock_session: MagicMock,
) -> None:
    """Test that rapid calls reuse cached device details."""
    mock_session.post.return_value = _mock_post_response(
        {
            "type": "http_get_result",
            "packet": [
                [
                    {"feature": "network.devicename", "value": "Living Room"},
                    {"feature": "network.connectiontype", "value": "wired"},
                    {"feature": "network.internet", "value": "connected"},
                    {
                        "feature": "network.macaddress_wired",
                        "value": "aa:bb:cc:dd:ee:ff",
                    },
                    {
                        "feature": "network.macaddress_wireless",
                        "value": "11:22:33:44:55:66",
                    },
                ],
                [{"feature": "inet4.ipaddress", "value": "192.168.1.100"}],
                [{"feature": "inet6.ipaddress", "value": "fe80::1"}],
                [{"feature": "wlan.strength", "value": "good"}],
            ],
        }
    )

    # Call 7 times in rapid succession (simulating 7 sensor updates)
    results = [await http_client.async_get_device_details() for _ in range(7)]

    # All results should be identical
    for r in results:
        assert r.device_name == "Living Room"

    # Only 1 actual HTTP call should have been made
    assert mock_session.post.call_count == 1


async def test_device_details_cache_expires(
    http_client: BraviaHttpClient,
    mock_session: MagicMock,
) -> None:
    """Test that cache expires and a fresh call is made."""
    mock_session.post.return_value = _mock_post_response(
        {
            "type": "http_get_result",
            "packet": [
                [
                    {"feature": "network.devicename", "value": "Room A"},
                    {"feature": "network.connectiontype", "value": "wired"},
                    {"feature": "network.internet", "value": "connected"},
                    {
                        "feature": "network.macaddress_wired",
                        "value": "aa:bb:cc:dd:ee:ff",
                    },
                    {
                        "feature": "network.macaddress_wireless",
                        "value": "11:22:33:44:55:66",
                    },
                ],
                [{"feature": "inet4.ipaddress", "value": "192.168.1.100"}],
                [{"feature": "inet6.ipaddress", "value": "fe80::1"}],
                [{"feature": "wlan.strength", "value": "good"}],
            ],
        }
    )

    result1 = await http_client.async_get_device_details()
    assert result1.device_name == "Room A"
    assert mock_session.post.call_count == 1

    # Expire the cache by moving time forward
    http_client._device_details_cache_time -= 60

    result2 = await http_client.async_get_device_details()
    assert result2.device_name == "Room A"
    assert mock_session.post.call_count == 2
