import base64
import json
from pathlib import Path
from unittest.mock import Mock
import pytest
from smart_tray.rgbic_capture import (capture_frame,format_hint,Observation,SceneReader,
    scene_definition,save_report,MASKED_ID)
from smart_tray.interactive_adapters import load_interactive_adapters

ROOT=Path(__file__).parent / "fixtures/config"
DEFINITION=scene_definition(ROOT/'diagnostics/led-research/schema-current.json')
RAW='010203040500000064007864'


def frame(**extras):
    return capture_frame({'dps':{'20':True,'21':'scene','24':'000003e803e8',
        '26':0,'46':1000,'47':200,'53':100,**extras}})


def observation(*frames):
    value=Observation('Neon World',DEFINITION)
    for f in frames:
        value.add(f)
    return value


def test_own_product_model_keeps_cloud_ability_distinct_from_lan_mapping():
    assert DEFINITION['dp']=='51' and DEFINITION['max_bytes']==128
    assert DEFINITION['mapping']=='ability_requires_lan_observation'


def test_raw_snapshot_preserves_exact_values_types_and_omits_response_metadata():
    f=capture_frame({'local_key':'synthetic-key','token':'synthetic-token',
        'dps':{'20':True,'46':1000,'51':RAW}})
    assert f.values['51']=={'type':'str','value':RAW,'format':{'encoding':'hex','byte_length':12}}
    assert f.values['20']['type']=='bool' and f.values['46']['type']=='int'
    assert 'synthetic' not in json.dumps(f.values)


@pytest.mark.parametrize('value', ['synthetic-secret',{'access_secret':'synthetic-secret'},
    '{"local_key":"not-for-report"}',r'{"\u0074oken":"hidden"}',
    ['prefix-synthetic-secret-suffix'],b'synthetic-secret','x'*8193,float('nan')])
def test_sensitive_and_unbounded_dp_values_are_never_preserved(value):
    f=capture_frame({'dps':{'51':value}},('synthetic-secret',))
    assert f.values['51'].get('omitted')=='unsafe_or_oversized'
    assert 'value' not in f.values['51']


def test_baseline_full_samples_only_changes_and_candidate_never_validated(tmp_path):
    o=observation(frame(),frame(**{'51':RAW}),frame(**{'51':RAW}))
    r=o.report()
    assert set(r['baseline'])=={'20','21','24','26','46','47','53'}
    assert set(r['changes'])=={'51'}
    assert r['samples'][1]['changes']=={}
    assert r['candidate']['command']=={'51':RAW}
    assert r['candidate']['approval_required'] and not r['candidate']['write_validated']
    assert not r['write_validated'] and r['writes_sent']==0
    path=save_report(tmp_path,r)
    assert json.loads(path.read_text(encoding='utf-8'))==r
    assert not list(tmp_path.glob('*.tmp'))


def test_only_mode_change_cannot_identify_the_effect():
    r=observation(frame(**{'21':'colour'}),frame(),frame()).report()
    assert set(r['changes'])=={'21'} and r['candidate'] is None


def test_no_observable_changes_is_not_treated_as_incompatibility():
    r=observation(frame(),frame(),frame()).report()
    assert not r['changes'] and r['candidate'] is None
    assert r['confidence']=='no_observable_evidence'


def test_continuous_payload_changes_are_not_ready_for_one_shot_replay():
    r=observation(frame(),*(frame(**{'51':'0102'+v}) for v in ('0001','0002','0003'))).report()
    assert r['changes']['51']['continuously_changing'] and r['candidate'] is None


@pytest.mark.parametrize('payload,eligible', [('01'*128,True),('01'*129,False),('arbitrary text',False)])
def test_candidate_obeys_own_schema_byte_limit_and_binary_encoding(payload,eligible):
    r=observation(frame(),frame(**{'51':payload}),frame(**{'51':payload})).report()
    assert bool(r['candidate']) is eligible


def test_base64_payload_is_preserved_without_implicit_transport_conversion():
    payload=base64.b64encode(bytes.fromhex(RAW)).decode()
    r=observation(frame(),frame(**{'51':payload}),frame(**{'51':payload})).report()
    assert format_hint(payload)['encoding']=='base64'
    assert r['candidate']['command']=={'51':payload}
    assert r['candidate']['encoding_conversion_performed'] is False


@pytest.mark.parametrize('condition', ['single_sample','power_changed','not_scene','failed','cancelled','no_schema'])
def test_incomplete_or_conflicting_evidence_never_produces_replay_candidate(condition):
    o=observation(frame(),frame(**{'51':RAW}),frame(**{'51':RAW}))
    if condition=='single_sample': o.frames.pop()
    if condition=='power_changed': o.frames[-1]=frame(**{'20':False,'51':RAW})
    if condition=='not_scene': o.frames[-1]=frame(**{'21':'music','51':RAW})
    if condition=='no_schema': o.definition=None
    r=o.report(condition if condition in ('failed','cancelled') else 'completed')
    assert r['candidate'] is None


@pytest.mark.parametrize('dp', ['20','21','24','26','46','47','53'])
def test_known_non_scene_dps_never_become_scene_commands(dp):
    o=observation(frame(),frame(**{dp:RAW}),frame(**{dp:RAW}))
    o.definition={**DEFINITION,'dp':dp}
    assert o.report()['candidate'] is None


def test_scene_reader_uses_only_status_and_closes_socket_without_writes():
    adapter=load_interactive_adapters(ROOT)['led']
    adapter.base.store=Mock()
    adapter.base.store.load.return_value='synthetic-local-key'
    device=Mock()
    device.status.return_value={'dps':{'20':True,'21':'scene','51':RAW}}
    adapter.base.factory=Mock(return_value=device)
    f=SceneReader(adapter).capture()
    assert f.values['51']['value']==RAW and f.state.connection=='online'
    assert [c[0] for c in device.mock_calls]==['status','close']
    assert adapter.base.store.load.call_count==1


def test_reader_suppresses_encoded_credentials_too():
    adapter=load_interactive_adapters(ROOT)['led']
    key='synthetic-local-key'
    adapter.base.store=Mock(); adapter.base.store.load.return_value=key
    device=Mock()
    device.status.return_value={'dps':{'20':True,'51':key.encode().hex(),
        '52':base64.b64encode(key.encode()).decode()}}
    adapter.base.factory=Mock(return_value=device)
    values=SceneReader(adapter).capture().values
    assert all('value' not in values[dp] for dp in ('51','52'))


def test_wrong_device_schema_is_rejected(tmp_path):
    path=tmp_path/'schema.json'
    path.write_text(json.dumps({'device_id_masked':'other','queries':[]}))
    assert scene_definition(path) is None
    assert MASKED_ID.startswith('exampl')
