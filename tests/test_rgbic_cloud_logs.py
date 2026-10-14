from urllib.parse import parse_qs, urlsplit
from unittest.mock import Mock
import pytest
from smart_tray.rgbic_cloud_logs import START, END, collect_logs
from smart_tray.led_research import LED_ID


def response(*logs, **extras):
    return {'success': True, 'result': {'device_id': LED_ID, 'logs': list(logs), 'has_next': False, **extras}}


def event(kind=5, code='dreamlight_scene_mode', value='010203040500000064007864'):
    return {'event_time': START+1000, 'event_id': kind, 'event_from': '2', 'code': code, 'value': value}


def test_exact_official_get_window_and_command_report_distinction():
    cloud=Mock(); cloud._tuyaplatform.return_value=response(event(), event(7))
    report=collect_logs(cloud, intervals=[{'scene':'Neon World','start':START,'end':END}])
    uri=cloud._tuyaplatform.call_args.args[0]
    assert uri==f'cloud/thing/{LED_ID}/logs'
    params=cloud._tuyaplatform.call_args.kwargs['query']
    assert params['type']=='5,7' and params['start_time']==START
    assert params['end_time']==END and params['query_type']==1
    assert cloud._tuyaplatform.call_args.kwargs['action']=='GET'
    assert cloud._tuyaplatform.call_args.kwargs['ver']=='v2.0'
    assert report['logs_found']==2 and report['sending_count']==report['report_count']==1
    assert report['dreamlight_scene_mode_count']==2
    assert report['logs'][0]['scene_interval_matches']==['Neon World']
    assert not report['logs'][0]['smart_life_origin_confirmed']
    assert not report['replay_ready'] and report['writes_sent']==0


def test_empty_is_different_from_denied():
    cloud=Mock(); cloud._tuyaplatform.return_value=response()
    empty=collect_logs(cloud)
    assert empty['query_result']=='read_ok' and empty['logs_found']==0
    assert '4g' in empty['next_step']
    cloud._tuyaplatform.return_value={'success':False,'msg':'access_secret=private'}
    denied=collect_logs(cloud)
    assert denied['query_result']=='denied_or_unavailable'
    assert denied['next_step']=='resolve_query_access_or_completeness_first'
    assert 'private' not in str(denied)


def test_mismatched_device_discards_all_rows():
    cloud=Mock(); cloud._tuyaplatform.return_value=response(event(),device_id='other')
    report=collect_logs(cloud)
    assert report['query_result']=='device_mismatch' and not report['logs']


def test_sanitization_keeps_raw_but_rejects_credentials_and_unrelated_events():
    cloud=Mock(); cloud._tuyaplatform.return_value=response(event(),event(value='synthetic-secret'),
        event(value={'local_key':'private'}),event(kind=1),event(code='access_secret'))
    report=collect_logs(cloud,('synthetic-secret',))
    assert report['logs_found']==1 and report['omitted_records']==4
    assert report['logs'][0]['format']=={'encoding':'hex','byte_length':12}
    assert 'synthetic-secret' not in str(report) and 'private' not in str(report)


def test_pagination_and_duplicate_records():
    cloud=Mock(); cloud._tuyaplatform.side_effect=[response(event(),has_next=True,current_row_key='cursor'),response(event(),event(7))]
    report=collect_logs(cloud)
    assert report['query_result']=='read_ok' and report['pages']==2 and report['logs_found']==2
    assert cloud._tuyaplatform.call_args.kwargs['query']['start_row_key']=='cursor'


def test_unavailable_cursor_marks_partial_instead_of_empty():
    cloud=Mock(); cloud._tuyaplatform.return_value=response(has_next=True)
    report=collect_logs(cloud)
    assert report['query_result']=='partial' and '4g' not in report['next_step']


@pytest.mark.parametrize('options',[{'device_id':'other'},{'start':END,'end':START},{'start':START,'end':START+900000}])
def test_rejects_other_devices_and_unbounded_queries(options):
    cloud=Mock()
    with pytest.raises(ValueError): collect_logs(cloud,**options)
    cloud._tuyaplatform.assert_not_called()
