from dataclasses import replace
import json
from pathlib import Path
import pytest
from smart_tray.rgbic_scene_protocol import (SceneColor, SceneFrame, decode_scene,
    encode_scene, decode_scene_hex, encode_scene_hex)


EXAMPLES = json.loads((Path(__file__).parent/'fixtures/tuya_ray_scene_examples.json').read_text(encoding='utf-8'))['examples']


@pytest.mark.parametrize('example', EXAMPLES, ids=lambda e: e['name'])
def test_published_examples_roundtrip_exactly(example):
    value = example['payload_hex']
    frame = decode_scene_hex(value)
    assert encode_scene_hex(frame) == value
    assert encode_scene(frame) == bytes.fromhex(value)
    assert decode_scene(encode_scene(frame)) == frame
    assert example['write_validated'] is False
    assert example['device_compatibility'] == 'unverified'


def test_known_published_thanksgiving_fields():
    frame = decode_scene_hex(EXAMPLES[0]['payload_hex'])
    assert (frame.version,frame.scene_id,frame.mode)==(1,37,10)
    assert (frame.interval_time,frame.change_time,frame.brightness)==(72,72,100)
    assert frame.colors == (SceneColor(61,100),SceneColor(268,91),SceneColor(186,73),SceneColor(23,97))
    assert frame.options['loop']==1 and frame.options['excessive']==1


def test_lossless_independent_times_reserved_fields_and_two_expand_bits():
    frame = replace(decode_scene_hex(EXAMPLES[0]['payload_hex']),
        change_time=12, option_a=0b10111111, option_b=17, option_c=23)
    assert frame.options == {'segmented':1,'loop':0,'excessive':1,'direction':1,
        'expand':3,'reserved1':1,'reserved2':1}
    assert decode_scene(encode_scene(frame))==frame


def test_mixed_scene_ids_are_preserved_without_guessing_names():
    frame=replace(decode_scene_hex(EXAMPLES[0]['payload_hex']),mode=20,option_a=2,option_b=3,option_c=4)
    assert frame.options == {'mixed_ids':(2,3,4)}
    assert decode_scene_hex(encode_scene_hex(frame))==frame


@pytest.mark.parametrize('changes', [
    {'version':2},{'mode':256},{'scene_id':-1},{'scene_id':True},
    {'interval_time':101},{'change_time':-1},{'brightness':101},
    {'option_a':256},{'option_b':-1},{'option_c':'0'}, {'colors':[]}])
def test_invalid_fields_are_rejected_without_silent_truncation(changes):
    with pytest.raises(ValueError):
        replace(decode_scene_hex(EXAMPLES[0]['payload_hex']),**changes)


@pytest.mark.parametrize('hue,saturation', [(361,100),(-1,50),(120,101),(120,-1),(True,1),(1,1.5)])
def test_invalid_colors(hue,saturation):
    with pytest.raises(ValueError): SceneColor(hue,saturation)


@pytest.mark.parametrize('value', ['', '01', '00'*129, '01'*10, 'zz'*12,
    '01 '*12, 'AQAAAA==', '1'*25, None])
def test_malformed_hex_and_non_hex_are_rejected(value):
    with pytest.raises(ValueError): decode_scene_hex(value)


def test_size_boundary_and_empty_palette():
    frame=decode_scene_hex(EXAMPLES[0]['payload_hex'])
    maximum=replace(frame,colors=(SceneColor(360,100),)*39)
    assert len(encode_scene(maximum))==126
    assert decode_scene(encode_scene(maximum))==maximum
    with pytest.raises(ValueError):replace(frame,colors=(SceneColor(0,0),)*40)
    empty=replace(frame,colors=())  # Upstream formatter permits an empty palette.
    assert decode_scene(encode_scene(empty))==empty
    with pytest.raises(ValueError):decode_scene(encode_scene(frame)+b'\x00')
    with pytest.raises(ValueError):decode_scene(bytearray(encode_scene(frame)))


def test_reference_catalog_does_not_claim_neon_world_or_outsmart_support():
    assert len(EXAMPLES)==6
    assert not any(e['name'].casefold()=='neon world' for e in EXAMPLES)
    assert all(not e['write_validated'] and e['device_compatibility']=='unverified' for e in EXAMPLES)
