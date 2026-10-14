import contextlib
import importlib.util
import json
import pytest
from pathlib import Path
from unittest.mock import Mock
from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication, QComboBox, QLineEdit
from test_interface import wait_until
from smart_tray.rgbic_cloud_logs import collect_logs


@pytest.mark.parametrize('cloud_window', [None, (1791838710000,1791838890000)])
def test_existing_form_uses_us_masks_credentials_and_queries_only_cloud(qt_app,tmp_path,cloud_window):
    spec=importlib.util.spec_from_file_location('rgbic_logs_ui',Path(__file__).parents[1]/'scripts/diagnose_led.py')
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    cloud=Mock(token='synthetic-token')
    cloud._tuyaplatform.return_value={'success':True,'result':{'logs':[],'has_next':False}}
    connections=[]
    def connect(*values, **kwargs):
        assert kwargs == {'single_attempt': True}
        connections.append(values)
        return contextlib.nullcontext(cloud)
    module.cloud_connection=connect
    reader=Mock()
    if cloud_window:
        (tmp_path/'cloud-logs-current.json').write_text(json.dumps({
            'window':{'start_ms':1,'end_ms':2}, 'logs_found':8, 'sending_count':5,
            'report_count':3,'dreamlight_scene_mode_count':0,
            'logs':[{'code':'work_mode'}]}),encoding='utf-8')
    window=module.ResearchWindow(reader,tmp_path,cloud_logs=True,cloud_window=cloud_window)
    def fill():
        dialog=QApplication.activeModalWidget()
        region=dialog.findChild(QComboBox,'cloudRegion')
        assert region.currentText()=='us' and not region.isEnabled()
        for name,value in [('cloudAccessId','synthetic-id'),('cloudAccessSecret','synthetic-secret')]:
            field=dialog.findChild(QLineEdit,name)
            assert field.echoMode()==QLineEdit.EchoMode.Password
            field.setText(value)
        dialog.accept()
    QTimer.singleShot(30,fill)
    window.schema_dialog()
    wait_until(qt_app,lambda:window.task is None)
    report=json.loads((tmp_path/'cloud-logs-current.json').read_text(encoding='utf-8'))
    assert report['query_result']=='read_ok' and report['logs_found']==0
    if cloud_window:
        assert report['window']=={'start_ms':cloud_window[0],'end_ms':cloud_window[1]}
        assert cloud._tuyaplatform.call_args.kwargs['query']['start_time']==cloud_window[0]
        assert report['comparison_previous']['previous_counts']['logs_found']==8
        assert (tmp_path/'cloud-logs-1-2.json').exists()
        assert report['next_step']=='inspect_nonstandard_dp_log_coverage_no_repeat_4g_capture'
    assert connections==[('us','synthetic-id','synthetic-secret')]
    assert not (tmp_path/'schema-current.json').exists()
    assert 'synthetic' not in window.output.toPlainText()
    reader.capture.assert_not_called();reader.write.assert_not_called()
    window.close();window.pool.waitForDone(3000);window.deleteLater()
