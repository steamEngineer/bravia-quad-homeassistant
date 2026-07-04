"""Tests for StartNotifyStates delta decoder."""

from custom_components.bravia_quad.grpc.notify_decode import decode_notify_delta

# Live capture: volume 50 after TCP bump (fw 001.454)
VOLUME_50_HEX = (
    "0a0e0a0c0a06766f6c756d6512020832"
    "122053117cf8b42ef7a89f371309801750bed9357a0981791d55446563d8262d277"
    "11a2461663538343932632d656164382d343862392d386631612d396536633566373331663032"
)


def test_decode_volume_delta() -> None:
    path, value = decode_notify_delta(VOLUME_50_HEX)
    assert path == "volume"
    assert value == 50


def test_decode_from_bytes() -> None:
    minimal = bytes.fromhex("0a0e0a0c0a06766f6c756d6512020832")
    path, value = decode_notify_delta(minimal)
    assert path == "volume"
    assert value == 50
