"""Allowlisted error evidence; never retain bodies, headers or secret messages."""
import re

CATEGORIES = {
    '1004': 'signature_invalid', '1001': 'credential_invalid', '1005': 'client_id_invalid',
    '1010': 'token_expired', '1011': 'token_invalid', '1400': 'token_invalid',
    '1013': 'request_time_invalid', '1106': 'api_or_device_permission_denied',
    '1114': 'ip_not_allowlisted', '2007': 'cross_region_access_denied',
    '28841001': 'cloud_plan_not_subscribed', '28841002': 'cloud_plan_expired',
    '28841003': 'cloud_plan_overdue', '28841004': 'cloud_plan_quota_exhausted',
    '28841101': 'api_not_subscribed', '28841102': 'api_subscription_expired',
    '28841103': 'api_subscription_overdue', '28841104': 'api_quota_exhausted',
    '28841105': 'project_not_authorized_for_api', '28841106': 'api_not_subscribed',
    '60009001': 'api_not_in_permission_package', '1100': 'parameter_missing',
    '1101': 'parameter_out_of_range', '1102': 'parameter_null', '1104': 'parameter_type_invalid',
}


def failure_evidence(response=None, http_status=None, *, exception=None, sensitive=()):
    http = http_status if type(http_status) is int and 100 <= http_status <= 599 else None
    code = None
    if isinstance(response, dict):
        raw = response.get('code', response.get('error_code'))
        if type(raw) in (str, int) and re.fullmatch(r'[0-9]{1,12}', str(raw)):
            if not any(s and str(s) in str(raw) for s in sensitive):
                code = str(raw)
    category = CATEGORIES.get(code, 'unclassified_tuya_error' if code else 'unclassified_failure')
    if not code:
        if http == 404:
            category = 'http_not_found'
        elif http in (401,403):
            category = 'http_authentication_or_access_denied'
        elif http and http >= 500:
            category = 'http_server_error'
        elif exception in ('Timeout','ConnectTimeout','ReadTimeout'):
            category = 'transport_timeout'
        elif exception in ('ConnectionError','SSLError'):
            category = 'transport_connection_error'
        elif exception in ('KeyError','TypeError','AttributeError','ValueError'):
            category = 'response_schema_or_client_error'
    return {'http_status': http, 'tuya_error_code': code, 'category': category,
        'message_sanitized': category.replace('_', ' '),
        'message_source': 'allowlisted_classification_not_original_server_text',
        'raw_message_saved': False, 'response_body_saved': False,
        'http_missing': http is None, 'tuya_code_missing': code is None}
