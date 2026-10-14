"""Offline codec for Tuya Ray Materials dreamlight_scene_mode version 1.

Reference commit: 83e20f5fe193a48245f521ff7119a53bafa989d1.
This module deliberately has no device, credential, UI or network dependency.
Wire fields are preserved independently: unlike the upstream convenience parser,
change_time and option B/C are never discarded. Structural validity does not
establish compatibility with a product or authorize a device command.
See diagnostics/rgbic-scenes/protocol-investigation.md and THIRD_PARTY_NOTICES.md.
"""
from dataclasses import dataclass
import re

MAX_BYTES = 128
HEADER_BYTES = 9


def _integer(value, low, high, field):
    if type(value) is not int or not low <= value <= high:
        raise ValueError(f'Invalid {field}')


@dataclass(frozen=True)
class SceneColor:
    hue: int  # Big-endian uint16, 0..360 degrees.
    saturation: int  # Wire percent 0..100, not panel-sdk units 0..1000.

    def __post_init__(self):
        _integer(self.hue, 0, 360, 'hue')
        _integer(self.saturation, 0, 100, 'saturation')


@dataclass(frozen=True)
class SceneFrame:
    scene_id: int
    mode: int
    interval_time: int
    change_time: int
    option_a: int
    option_b: int
    option_c: int
    brightness: int  # Wire percent 0..100.
    colors: tuple[SceneColor, ...]
    version: int = 1

    def __post_init__(self):
        _integer(self.version, 1, 1, 'version (only version 1 verified offline)')
        for field in ('scene_id', 'mode', 'option_a', 'option_b', 'option_c'):
            _integer(getattr(self, field), 0, 255, field)
        for field in ('interval_time', 'change_time', 'brightness'):
            _integer(getattr(self, field), 0, 100, field)
        if type(self.colors) is not tuple or any(type(c) is not SceneColor for c in self.colors):
            raise ValueError('Invalid colors')
        if HEADER_BYTES + 3 * len(self.colors) > MAX_BYTES:
            raise ValueError('Scene exceeds 128 bytes')

    @property
    def options(self):
        if self.mode == 20:
            return {'mixed_ids': (self.option_a, self.option_b, self.option_c)}
        return {'segmented': (self.option_a >> 7) & 1,
            'loop': (self.option_a >> 6) & 1,
            'excessive': (self.option_a >> 5) & 1,
            'direction': (self.option_a >> 4) & 1,
            'expand': (self.option_a >> 2) & 3,
            'reserved1': (self.option_a >> 1) & 1,
            'reserved2': self.option_a & 1}


def decode_scene(payload: bytes) -> SceneFrame:
    """Decode exact bytes, rejecting unknown versions and malformed color units."""
    if type(payload) is not bytes or not HEADER_BYTES <= len(payload) <= MAX_BYTES:
        raise ValueError('Invalid scene byte length')
    if (len(payload) - HEADER_BYTES) % 3:
        raise ValueError('Incomplete color unit')
    version, scene_id, mode, interval, change, a, b, c, brightness = payload[:HEADER_BYTES]
    colors = tuple(SceneColor(int.from_bytes(payload[i:i+2], 'big'), payload[i+2])
        for i in range(HEADER_BYTES, len(payload), 3))
    return SceneFrame(scene_id, mode, interval, change, a, b, c, brightness, colors, version)


def encode_scene(scene: SceneFrame) -> bytes:
    """Encode a validated frame; no implicit defaults or transport encoding."""
    if type(scene) is not SceneFrame:
        raise ValueError('Expected SceneFrame')
    scene.__post_init__()
    header = bytes((scene.version, scene.scene_id, scene.mode, scene.interval_time,
        scene.change_time, scene.option_a, scene.option_b, scene.option_c, scene.brightness))
    return header + b''.join(c.hue.to_bytes(2, 'big') + bytes((c.saturation,)) for c in scene.colors)


def decode_scene_hex(value: str) -> SceneFrame:
    """Panel formatter boundary: strict hex, never guess Base64 or whitespace."""
    if type(value) is not str or not 18 <= len(value) <= 2 * MAX_BYTES:
        raise ValueError('Invalid hex length')
    if len(value) % 2 or not re.fullmatch('[0-9a-fA-F]+', value):
        raise ValueError('Invalid scene hex')
    return decode_scene(bytes.fromhex(value))


def encode_scene_hex(scene: SceneFrame) -> str:
    return encode_scene(scene).hex()
