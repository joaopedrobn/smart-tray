import hashlib
import hmac
import json
from unittest.mock import Mock
from urllib.parse import urlsplit
import pytest
import requests
from smart_tray.cloud_evidence import failure_evidence
from smart_tray.diagnostic import cloud_connection
from smart_tray.rgbic_cloud_logs import START, END, collect_logs
from smart_tray.led_research import LED_ID


@pytest.mark.parametrize('code,category',[
    ('1004','signature_invalid'),('1106','api_or_device_permission_denied'),
    ('28841105','project_not_authorized_for_api'),('28841101','api_not_subscribed'),
    ('28841002','cloud_plan_expired'),('60009001','api_not_in_permission_package'),
    ('2007','cross_region_access_denied'),('1101','parameter_out_of_range')])
def test_distinct_business_errors_are_preserved_without_raw_message(code,category):
    value=failure_evidence({'code':code,'msg':'Access Secret private-value','token':'private-token'},403)
    assert value['tuya_error_code']==code and value['category']==category
    assert value['http_status']==403
    assert 'private' not in json.dumps(value)


def test_missing_http_is_unknown_and_sensitive_error_code_is_omitted():
    value=failure_evidence({'error_code':'123456'},None,sensitive=('123456',))
    assert value['http_status'] is None and value['http_missing']
    assert value['tuya_error_code'] is None


def test_http_and_local_errors_are_not_mislabeled_as_empty_records():
    assert failure_evidence(http_status=404)['category']=='http_not_found'
    assert failure_evidence(exception='ReadTimeout')['category']=='transport_timeout'
    assert failure_evidence(exception='KeyError')['category']=='response_schema_or_client_error'


def test_real_tinytuya_signer_and_http_evidence_with_fully_simulated_http(monkeypatch):
    def http(status,body):
        response=requests.Response();response.status_code=status
        response._content=json.dumps(body).encode()
        return response
    session=Mock()
    session.__enter__=Mock(return_value=session);session.__exit__=Mock(return_value=False)
    session.get.side_effect=[http(200,{'success':True,'result':{'access_token':'test-token'}}),
        http(403,{'success':False,'code':28841105,'msg':'Project not authorized synthetic-secret'})]
    monkeypatch.setattr(requests,'Session',Mock(return_value=session))
    with cloud_connection('us','test-id','synthetic-secret') as cloud:
        report=collect_logs(cloud,('test-id','synthetic-secret',cloud.token))
    assert session.get.call_count==2
    args,kwargs=session.get.call_args
    url=args[0];headers=kwargs['headers']
    assert url.startswith(f'https://openapi.tuyaus.com/v2.0/cloud/thing/{LED_ID}/logs?')
    assert urlsplit(url).query==f'end_time={END}&query_type=1&size=100&start_time={START}&type=5%2C7'
    canonical=f'/v2.0/cloud/thing/{LED_ID}/logs?end_time={END}&query_type=1&size=100&start_time={START}&type=5,7'
    to_sign='GET\n'+hashlib.sha256(b'').hexdigest()+'\n\n'+canonical
    expected=hmac.new(b'synthetic-secret',('test-idtest-token'+headers['t']+to_sign).encode(),hashlib.sha256).hexdigest().upper()
    assert headers['sign']==expected
    assert kwargs['allow_redirects'] is False and kwargs['timeout']==(5,15)
    assert report['failure']['http_status']==403
    assert report['failure']['tuya_error_code']=='28841105'
    assert report['failure']['category']=='project_not_authorized_for_api'
    assert report['pages']==0 and 'synthetic-secret' not in json.dumps(report)


def test_single_attempt_blocks_tinytuya_token_refresh(monkeypatch):
    def http(body):
        response=requests.Response(); response.status_code=200
        response._content=json.dumps(body).encode()
        return response
    session=Mock()
    session.__enter__=Mock(return_value=session); session.__exit__=Mock(return_value=False)
    session.get.side_effect=[http({'success':True,'result':{'access_token':'test-token'}}),
        http({'success':False,'code':1011,'msg':'token invalid'})]
    monkeypatch.setattr(requests,'Session',Mock(return_value=session))
    with cloud_connection('us','test-id','synthetic-secret',single_attempt=True) as cloud:
        report=collect_logs(cloud, max_pages=1)
    assert session.get.call_count==2  # One authentication and one log request, no renewal.
    assert report['failure']['tuya_error_code']=='1011'
    assert report['failure']['message_sanitized']=='token invalid'


def test_single_page_does_not_fetch_more_or_claim_completeness():
    cloud=Mock()
    cloud._tuyaplatform.return_value={'success':True,'result':{
        'logs':[], 'has_next':True, 'current_row_key':'next'}}
    report=collect_logs(cloud,max_pages=1)
    assert cloud._tuyaplatform.call_count==1
    assert report['query_result']=='partial' and report['pages']==1
