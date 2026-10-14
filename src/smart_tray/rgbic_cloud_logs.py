"""Bounded official GET-only LED log query; never a replay transport."""
from datetime import datetime, timezone
import base64
import json
import re
import time
from .led_research import LED_ID
from .rgbic_capture import MASKED_ID, safe_raw, format_hint, now
from .cloud_evidence import failure_evidence

START = int(datetime(2026, 10, 12, 20, 17, 30, tzinfo=timezone.utc).timestamp()*1000)
END = int(datetime(2026, 10, 12, 20, 21, tzinfo=timezone.utc).timestamp()*1000)


def collect_logs(cloud, sensitive=(), *, device_id=LED_ID, start=START, end=END, intervals=(), max_pages=10):
    if device_id != LED_ID or type(start) is not int or type(end) is not int or not 0 < end-start <= 600_000:
        raise ValueError('Only identified LED and bounded time window allowed')
    protected = tuple(s for s in sensitive if isinstance(s, str) and s)
    protected += tuple(s.encode().hex() for s in protected) + tuple(base64.b64encode(s.encode()).decode() for s in protected)
    rows, seen, cursor = [], set(), ''
    outcome, omitted, pages = 'partial', 0, 0
    failure = None
    transport = getattr(cloud, '_smart_tray_http_evidence', None)
    transport = transport if isinstance(transport, dict) else {}
    if type(max_pages) is not int or not 1 <= max_pages <= 10:
        raise ValueError('Invalid page limit')
    for _ in range(max_pages):
        params = dict(type='5,7', start_time=start, end_time=end, query_type=1, size=100)
        if cursor:
            params['start_row_key'] = cursor
        try:
            transport['http_status'] = None
            response = cloud._tuyaplatform(f'cloud/thing/{device_id}/logs', query=params, action='GET', ver='v2.0')
            if not isinstance(response, dict) or response.get('success') is not True:
                failure = failure_evidence(response, transport.get('http_status'), sensitive=protected)
                outcome = 'denied_or_unavailable' if not pages else 'partial'
                break
            result = response['result']
            if result.get('device_id', device_id) != device_id:
                outcome = 'device_mismatch'
                rows = []
                break
            logs = result['logs']
            if not isinstance(logs, list):
                raise ValueError('Unexpected response')
            pages += 1
            for item in logs:
                try:
                    instant = item['event_time']
                    event = int(item['event_id'])
                    code = item.get('code')
                    if type(instant) is not int or not start <= instant <= end or event not in (5, 7):
                        raise ValueError('Unexpected event')
                    if not isinstance(code, str) or not re.fullmatch(r'[a-zA-Z0-9_]{1,80}', code):
                        raise ValueError('Unexpected code')
                    value = safe_raw(item['value'], protected)
                    row = {'timestamp': datetime.fromtimestamp(instant/1000, timezone.utc).isoformat(),
                        'event_time': instant, 'event_id': event,
                        'kind': 'instruction_sending' if event == 5 else 'status_report',
                        'code': code, 'value': value, 'value_type': type(value).__name__, 'format': format_hint(value),
                        'event_from': str(item.get('event_from')) if str(item.get('event_from')) in ('1','2','3','4','-1') else 'unknown',
                        'smart_life_origin_confirmed': False,
                        'scene_interval_matches': [i['scene'] for i in intervals if i['start'] <= instant <= i['end']],
                        'scene_assignment': 'time_interval_correlation_only', 'write_validated': False}
                    dp = item.get('dp_id')
                    if str(dp).isdigit() and 0 < int(dp) <= 65535:
                        row['dp_id'] = int(dp)
                    status = item.get('status')
                    if str(status) in ('0','1','2','true','false'):
                        row['reported_status'] = str(status)
                    safe_raw(code, protected)
                    encoded = json.dumps(row, sort_keys=True)
                    if encoded not in seen:
                        seen.add(encoded); rows.append(row)
                except (ValueError, TypeError, KeyError, AttributeError):
                    omitted += 1
            if not result.get('has_next', False):
                outcome = 'read_ok'
                break
            following = result.get('current_row_key')
            if not isinstance(following, str) or not following or following == cursor or len(following)>1024:
                break
            cursor = following
            time.sleep(.25)  # Worker only; stay below the documented request rate.
        except Exception as exc:
            failure = getattr(exc, 'evidence', None) or failure_evidence(http_status=transport.get('http_status'), exception=type(exc).__name__)
            outcome = 'denied_or_unavailable' if not pages else 'partial'
            break  # Never log exception text, response objects or credentials.
    rows.sort(key=lambda r: r['event_time'])
    scene_rows = [r for r in rows if r['code']=='dreamlight_scene_mode']
    return {'timestamp': now(), 'device_id_masked': MASKED_ID, 'region': 'us',
        'window': {'start_ms': start, 'end_ms': end}, 'query_result': outcome, 'pages': pages,
        'failure': failure,
        'http_status': transport.get('http_status'),
        'logs_found': len(rows), 'omitted_records': omitted,
        'sending_count': sum(r['event_id']==5 for r in rows),
        'report_count': sum(r['event_id']==7 for r in rows),
        'dreamlight_scene_mode_count': len(scene_rows), 'logs': rows,
        'replay_ready': False, 'writes_sent': 0,
        'next_step': 'review_scene_commands' if any(r['event_id']==5 for r in scene_rows) else
            'one_4g_neon_world_experiment_if_query_complete' if outcome=='read_ok' and not omitted else
            'resolve_query_access_or_completeness_first'}


def capture_intervals(directory):
    intervals = []
    for path in directory.glob('*.json'):
        try:
            doc = json.loads(path.read_text(encoding='utf-8'))
            if doc.get('device_id_masked') != MASKED_ID:
                continue
            name = safe_raw(doc['scene'])
            intervals.append({'scene': name,
                'start': int(datetime.fromisoformat(doc['started_at']).timestamp()*1000),
                'end': int(datetime.fromisoformat(doc['ended_at']).timestamp()*1000)})
        except (OSError, ValueError, TypeError, KeyError, AttributeError):
            continue
    return intervals
