import copy
import json
import pytest
from smart_tray.rgbic_analysis import analyze_record, analyze_directory
from smart_tray.rgbic_capture import Observation
from test_rgbic_capture import frame, DEFINITION, RAW


def report(scene='Neon World', before='scene', after='scene', raw=False):
    value = Observation(scene, DEFINITION)
    first = frame(**{'21': before})
    first.timestamp = '2026-10-12T20:00:00+00:00'
    value.add(first)
    for seconds in (2, 13):
        item = frame(**{'21': after, **({'51': RAW} if raw else {})})
        item.timestamp = f'2026-10-12T20:00:{seconds:02d}+00:00'
        value.add(item)
    return json.loads(json.dumps(value.report()))


def test_mode_change_is_not_scene_raw_and_summary_is_recomputed():
    document = report(before='colour')
    document['changes'] = {'51': {'invented': True}}
    document['candidate'] = {'command': {'51': 'invented'}}
    result = analyze_record(document, DEFINITION)
    assert list(result['changes']) == ['21']
    assert result['candidate'] is None and not result['scene_raw_observed']
    assert result['changes']['21']['before']['value'] == 'colour'
    assert result['changes']['21']['after']['value'] == 'scene'
    assert not result['changes_last_10_seconds']
    assert not result['phase_boundary_recorded']


def test_known_hsv_string_is_not_confused_with_raw_scene_or_active_colour():
    result = analyze_record(report(), DEFINITION)
    assert result['known_hsv24']['hsv'] == {'h': 0, 's': 1000, 'v': 1000}
    assert not result['scene_raw_observed'] and result['scene_identifier'] is None
    assert result['candidate'] is None


def test_actual_raw_observation_can_be_a_candidate_but_never_validated():
    result = analyze_record(report(raw=True), DEFINITION)
    assert result['scene_raw_observed']
    assert result['candidate']['command'] == {'51': RAW}
    assert not result['candidate']['write_validated']
    assert result['analysis_performed_writes'] == 0


@pytest.mark.parametrize('mutation', ['wrong_before', 'wrong_type', 'wrong_count', 'reverse_time', 'secret'])
def test_invalid_or_unsafe_evidence_is_rejected(mutation):
    document = report(before='colour')
    if mutation == 'wrong_before':
        document['samples'][0]['changes']['21']['before']['value'] = 'music'
    elif mutation == 'wrong_type':
        document['baseline']['20']['type'] = 'str'
    elif mutation == 'wrong_count':
        document['sample_count'] = 42
    elif mutation == 'reverse_time':
        document['samples'][0]['timestamp'] = '2026-10-12T19:00:00+00:00'
    else:
        document['baseline']['24']['value'] = 'access_secret=synthetic-private-value'
    with pytest.raises(ValueError):
        analyze_record(document, DEFINITION)


def test_all_files_scanned_duplicates_distinct_from_indistinguishable_effects(tmp_path):
    documents = [report(), report('Dreamland'), report()]
    for i, document in enumerate(documents):
        (tmp_path/f'{i}.json').write_text(json.dumps(document), encoding='utf-8')
    (tmp_path/'invalid.json').write_text('invalid', encoding='utf-8')
    result = analyze_directory(tmp_path, DEFINITION)
    assert result['files_scanned'] == 4 and result['records_analyzed'] == 3
    assert len(result['rejected']) == 1 and result['sample_count_total'] == 9
    assert result['indistinguishable_final_state_groups'] == [['Neon World', 'Dreamland', 'Neon World']]
    assert result['duplicate_same_scene_trajectories'] == [['0.json', '2.json']]
    assert set(result['constant_dps_all_recordings']) == {'20', '21', '24', '26', '46', '47', '53'}
    assert result['scene_payloads_observed'] == 0 and not result['replay_validated']
    assert result['writes_sent'] == 0


def test_reconstruction_does_not_mutate_original_record():
    document = report(before='colour', raw=True)
    saved = copy.deepcopy(document)
    analyze_record(document, DEFINITION)
    assert document == saved
