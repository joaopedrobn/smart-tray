import copy
import json
from pathlib import Path
import shutil
import subprocess
import pytest
from smart_tray.rgbic_scene_library import import_library, PID, API

ROOT = Path(__file__).resolve().parents[1]
EXAMPLE = json.loads((ROOT/'tests/fixtures/tuya_ray_scene_examples.json').read_text(encoding='utf-8'))['examples'][0]


def envelope(items=None):
    item = {'sceneName': 'Synthetic test scene', 'sceneId': 123,
        'dpCode': 'dreamlight_scene_mode', 'dpId': 51, 'sceneData': EXAMPLE['payload_hex']}
    return {'format': 'smart-tray-tuya-library-v1', 'status': 'read_ok',
        'source_api': API, 'source_version': '1.0', 'product_id': PID,
        'device_id_masked': 'exampl…0001',
        'binding_evidence': 'official_ide_context_matches_cached_cloud_metadata',
        'result': [{'plateName': 'Mood', 'plateId': 3, 'data': [{'items': items or [item]}]}]}


def parse(doc):
    return import_library(json.dumps(doc).encode())


def test_import_real_shaped_response_preserves_payload_and_separates_validation():
    doc = envelope()
    report = parse(doc)
    scene = report['scenes'][0]
    assert report['scene_count'] == 1 and report['category_counts']['Mood'] == 1
    assert scene['payload_hex'] == EXAMPLE['payload_hex'] and scene['codec_roundtrip_ok']
    assert scene['decoded']['scene_id'] == 37
    assert not scene['write_validated'] and not scene['lan_encoding_confirmed']
    assert not report['replay_ready'] and report['writes_sent'] == 0
    assert 'not_cryptographic_attestation' in report['source_kind']
    assert not report['neon_world_found']


@pytest.mark.parametrize('field,value', [('product_id','other'),('device_id_masked','other'),
    ('status','denied'),('source_api','other'),('source_version','2.0'),
    ('binding_evidence',None),('format','generic_example')])
def test_wrong_product_origin_and_failed_queries_cannot_import(field,value):
    doc = envelope(); doc[field] = value
    with pytest.raises(ValueError): parse(doc)


def test_empty_official_result_does_not_fall_back_to_generic_scenes():
    doc = envelope(); doc['result'] = []
    report = parse(doc)
    assert report['scene_count'] == 0 and not report['neon_world_found']


def test_bad_dp_raw_names_and_version_are_rejected_without_copying_private_fields():
    base = envelope()['result'][0]['data'][0]['items'][0]
    items = []
    for patch in ({'dpId':25},{'dpCode':'default_scene_data'},{'sceneData':'private-token'},
        {'sceneData':'02'+EXAMPLE['payload_hex'][2:]},{'sceneName':'bad\nname'}):
        items.append({**base, **patch, 'access_secret':'private-secret'})
    doc = envelope(items); doc['token'] = 'private-token'
    report = parse(doc)
    assert report['rejected_count'] == 5 and report['scene_count'] == 0
    assert 'private' not in json.dumps(report)


def test_duplicates_and_unknown_category_do_not_invent_mapping():
    item = envelope()['result'][0]['data'][0]['items'][0]
    doc = envelope([item,copy.deepcopy(item)]); doc['result'][0]['plateName'] = 'OEM custom category'
    report = parse(doc)
    assert report['scene_count'] == 1 and report['category_counts']['Unclassified'] == 1
    assert report['scenes'][0]['source_category'] == 'OEM custom category'


@pytest.mark.parametrize('raw', [b'not json',b'[]',b'0',b'x'*5_000_001], ids=['bad-json','array','number','oversized'])
def test_invalid_or_excessive_input_is_bounded(raw):
    with pytest.raises(ValueError):import_library(raw)


def test_official_ark_helper_with_fully_mocked_context_and_no_network():
    node = shutil.which('node')
    if not node: pytest.skip('Node not installed')
    module = (ROOT/'scripts/tuya_miniapp/recover_scene_library.mjs').as_uri()
    js = f"import {{recoverSceneLibrary}} from {json.dumps(module)};\n" + r'''
import assert from 'node:assert/strict';
let calls=0;
const values={debugMode_app:'real',current_debug_device_id_app:'example-led-0000000001',current_debug_product_id_app:'example-product-led'};
const ark={project:{getInfo:async()=>({id:'app'})},storage:{get:async k=>values[k]},
  auth:{getCustomerUserInfo:async()=>({access_token:'private-session'})},http:{atop:async options=>{
    calls++;assert.equal(options.api,'tuya.m.light.panel.library.data.get');
    assert.deepEqual(options.params,{bizId:'example-led-0000000001',bizType:0,libType:'SCENE_LIB',libVersion:'',libDataType:4});
    return {data:{success:true,result:[],access_token:'private-session'}};
  }}};
const empty=await recoverSceneLibrary(ark);assert.equal(calls,1);assert.equal(empty.status,'read_ok');
assert.deepEqual(empty.result,[]);assert.ok(!JSON.stringify(empty).includes('private-session'));
values.current_debug_product_id_app='wrong';
assert.equal((await recoverSceneLibrary(ark)).status,'context_mismatch');assert.equal(calls,1);
values.current_debug_product_id_app='example-product-led';
ark.http.atop=async()=>{calls++;throw new Error('private-session');};
const failure=await recoverSceneLibrary(ark);assert.equal(calls,2);assert.equal(failure.requests,1);
assert.ok(!JSON.stringify(failure).includes('private-session'));
'''
    js += '\nconst payload='+json.dumps(EXAMPLE['payload_hex'])+';\n' + r'''
ark.http.atop=async()=>({data:{success:true,result:[{plateName:'Mood',plateId:3,
  data:[{items:[{sceneName:'Synthetic fixture',sceneId:123,dpCode:'dreamlight_scene_mode',
    dpId:51,sceneData:payload,access_token:'private-session'}]}]}]}});
const result=await recoverSceneLibrary(ark);
assert.ok(!JSON.stringify(result).includes('private-session'));
console.log(JSON.stringify(result));
'''
    result=subprocess.run([node,'--input-type=module','-'],input=js.encode(),capture_output=True,check=True,timeout=15)
    imported=import_library(result.stdout)
    assert imported['scene_count']==1 and imported['scenes'][0]['codec_roundtrip_ok']
