"""Offline comparison of scene recordings. No device or credential access."""
from datetime import datetime
import hashlib
import json
from pathlib import Path
from .led_research import hsv16_decode
from .rgbic_capture import MASKED_ID, Frame, Observation, SCENES, safe_raw, format_hint


def timestamp(value):
    result = datetime.fromisoformat(value)
    if result.tzinfo is None:
        raise ValueError('Timezone required')
    return result


def snapshot(value):
    if not isinstance(value, dict) or not value:
        raise ValueError('Snapshot required')
    result = {}
    for dp, item in value.items():
        if not dp.isdigit() or not 0 < int(dp) <= 65535 or not isinstance(item, dict):
            raise ValueError('Invalid DP')
        if 'value' not in item:
            result[dp] = {'type': 'unavailable', 'omitted': 'unsafe_or_oversized'}
            continue
        raw = safe_raw(item['value'])
        if type(raw).__name__ != item.get('type'):
            raise ValueError('Inconsistent DP type')
        result[dp] = {'type': type(raw).__name__, 'value': raw, 'format': format_hint(raw)}
    return result


def fingerprint(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=True).encode()).hexdigest()


def analyze_record(document, definition=None):
    """Reconstruct snapshots from deltas; do not trust stored changes/candidate."""
    if document.get('device_id_masked') != MASKED_ID or document.get('scene') not in SCENES:
        raise ValueError('Unexpected device or scene')
    started = timestamp(document['started_at'])
    ended = timestamp(document['ended_at'])
    if ended < started:
        raise ValueError('Invalid recording interval')
    state = snapshot(document['baseline'])
    observation = Observation(document['scene'], definition)
    observation.add(Frame(document['started_at'], state.copy()))
    trajectory = [state.copy()]
    previous_time = started
    for sample in document['samples']:
        instant = timestamp(sample['timestamp'])
        if not previous_time <= instant <= ended:
            raise ValueError('Unordered samples')
        delta = sample['changes']
        if not isinstance(delta, dict):
            raise ValueError('Invalid delta')
        for dp, change in delta.items():
            before = snapshot({dp: change['before']})[dp] if change['before'] is not None else None
            after = snapshot({dp: change['after']})[dp] if change['after'] is not None else None
            if before != state.get(dp):
                raise ValueError('Delta disagrees with previous snapshot')
            if after is None:
                state.pop(dp, None)
            else:
                state[dp] = after
        observation.add(Frame(sample['timestamp'], state.copy()))
        if state != trajectory[-1]:
            trajectory.append(state.copy())
        previous_time = instant
    if len(observation.frames) != document['sample_count'] or previous_time != ended:
        raise ValueError('Incomplete recording')
    result = observation.report(document['status'])
    result['capture_reported_writes_sent'] = document.get('writes_sent')
    result['analysis_performed_writes'] = 0
    result['duration_seconds'] = round((ended-started).total_seconds(), 3)
    result['final_snapshot'] = state
    result['final_state_fingerprint'] = fingerprint(state)
    result['trajectory_fingerprint'] = fingerprint(trajectory)
    result['phase_boundary_recorded'] = 'observation_started_at' in document
    result['changes_last_10_seconds'] = [s for s in result['samples']
        if (ended-timestamp(s['timestamp'])).total_seconds() <= 10 and s['changes']]
    dp = definition['dp'] if definition else None
    result['scene_raw_observed'] = bool(dp and any(dp in f.values and 'value' in f.values[dp] for f in observation.frames))
    result['scene_identifier'] = None  # No guessed decoding of a generic Raw packet.
    colour = state.get('24', {}).get('value')
    try:
        result['known_hsv24'] = {'raw': colour, 'hsv': hsv16_decode(colour),
            'interpretation': 'stored_colour_not_scene_payload_or_current_effect_colour'}
    except (ValueError, TypeError):
        result['known_hsv24'] = None
    return result


def analyze_directory(directory, definition=None):
    records, rejected = [], []
    paths = sorted(Path(directory).glob('*.json'))
    for path in paths:
        try:
            if path.stat().st_size > 4_000_000:
                raise ValueError('File size limit')
            content = path.read_bytes()
            document = json.loads(content)
            record = analyze_record(document, definition)
            record['source_file'] = safe_raw(path.name)
            record['source_sha256'] = hashlib.sha256(content).hexdigest()
            records.append(record)
        except (OSError, ValueError, TypeError, KeyError, AttributeError):
            rejected.append({'file': hashlib.sha256(path.name.encode()).hexdigest(),
                'reason': 'invalid_or_unsafe_record'})
    records.sort(key=lambda r: r['started_at'])
    finals, repeats = {}, {}
    for r in records:
        finals.setdefault(r['final_state_fingerprint'], []).append(r['scene'])
        repeats.setdefault((r['scene'], r['trajectory_fingerprint']), []).append(r['source_file'])
    constant = {}
    all_frames = [r['baseline'] for r in records] + [r['final_snapshot'] for r in records]
    if all_frames:
        for dp, item in all_frames[0].items():
            if all(s.get(dp) == item for s in all_frames) and not any(dp in r['changes'] for r in records):
                constant[dp] = item
    return {'files_scanned': len(paths), 'records_analyzed': len(records), 'rejected': rejected,
        'sample_count_total': sum(r['sample_count'] for r in records), 'records': records,
        'schema_scene_definition': definition, 'constant_dps_all_recordings': constant,
        'indistinguishable_final_state_groups': [names for names in finals.values() if len(names)>1],
        'duplicate_same_scene_trajectories': [files for files in repeats.values() if len(files)>1],
        'captured_scenes': list(dict.fromkeys(r['scene'] for r in records)),
        'scene_payloads_observed': sum(r['scene_raw_observed'] for r in records),
        'replay_validated': False, 'writes_sent': 0}
