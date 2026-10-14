import json
import threading
import time
from unittest.mock import Mock
from PySide6.QtCore import QTimer
from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from test_quick_ui import quick,click,find
from test_interface import wait_until
from test_rgbic_capture import frame,RAW


def recorder(quick):
    panel,controller,_,values,_,_=quick
    r=panel.bridge.recorder
    r.interval_ms=20; r.observe_seconds=.15; r.prepare_seconds=2
    count=0
    def capture():
        nonlocal count
        count+=1
        return frame(**({'51':RAW} if count>1 else {}))
    r.reader=Mock(); r.reader.capture.side_effect=capture
    return r


def test_integrated_capture_saves_raw_candidate_and_never_writes(quick,qt_app):
    panel,controller,adapters,_,commands,_=quick
    r=recorder(quick)
    # Archived research backend remains testable without exposing production UI.
    panel.bridge.startSceneCapture()
    wait_until(qt_app,lambda:r.phase=='prepared')
    assert controller.led_observer is r and not controller.can_write('led',20)
    assert not panel.bridge.state['led']['colourEnabled']
    panel.bridge.concludeSceneCapture()
    wait_until(qt_app,lambda:r.phase=='saved')
    result=json.loads(open(r.path,encoding='utf-8').read())
    assert result['scene']=='Neon World' and result['candidate']['command']=={'51':RAW}
    assert result['writes_sent']==0 and not result['write_validated']
    assert controller.led_observer is None and 'led' not in controller.busy
    assert not commands
    assert all(not a.write.called for a in adapters.values())
    panel.bridge.nextDiscoveryScene()
    assert r.index==1 and r.phase=='idle'


def test_observation_serializes_led_reads_and_blocks_all_led_writers(quick,qt_app):
    panel,controller,adapters,_,commands,_=quick
    r=recorder(quick)
    assert r.start()
    wait_until(qt_app,lambda:r.phase=='prepared')
    reads=adapters['led'].read.call_count
    elgin_reads=adapters['elgin'].read.call_count
    controller.refresh()
    wait_until(qt_app,lambda:'elgin' not in controller.busy and 'novadigital' not in controller.busy)
    assert adapters['led'].read.call_count==reads
    assert adapters['elgin'].read.call_count>elgin_reads
    assert not controller.toggle('led',20)
    assert not controller.request_colour('007803e803e8')
    assert not controller.request_direct('led','mode','colour')
    assert not r.start() and not r.select(1)
    r.cancel()
    wait_until(qt_app,lambda:r.phase=='cancelled')
    assert not commands


def test_read_failure_stops_without_retries_or_secret_exception_text(quick,qt_app):
    r=recorder(quick)
    r.reader.capture.side_effect=RuntimeError('synthetic-secret-do-not-show')
    assert r.start()
    wait_until(qt_app,lambda:r.phase=='error')
    QTest.qWait(200)
    r.reader.capture.assert_called_once()
    assert 'synthetic-secret' not in json.dumps(r.view())
    assert quick[1].led_observer is None and not quick[4]


def test_cancellation_keeps_lease_until_inflight_read_finishes(quick,qt_app):
    r=recorder(quick)
    gate=threading.Event()
    r.reader.capture.side_effect=lambda: (gate.wait(2),frame())[1]
    try:
        assert r.start()
        wait_until(qt_app,lambda:r.reader.capture.called)
        r.cancel()
        assert r.phase=='cancelling' and quick[1].led_observer is r
        assert not quick[1].can_write('led',20)
    finally:
        gate.set()
    wait_until(qt_app,lambda:r.phase=='cancelled')
    assert quick[1].led_observer is None and not quick[4]


def test_hidden_panel_finishes_capture_in_workers_and_keeps_gui_responsive(quick,qt_app):
    panel,_,_,_,commands,_=quick
    r=recorder(quick)
    threads=[]
    original=r.reader.capture.side_effect
    def capture():
        threads.append(threading.get_ident())
        return original()
    r.reader.capture.side_effect=capture
    ticks=[]
    heartbeat=QTimer(); heartbeat.setInterval(10); heartbeat.timeout.connect(lambda:ticks.append(1)); heartbeat.start()
    try:
        r.start()
        wait_until(qt_app,lambda:r.phase=='prepared')
        panel.hide(); r.conclude()
        wait_until(qt_app,lambda:r.phase=='saved')
        assert not panel.isVisible() and len(ticks)>5
        assert threads and all(t!=threading.get_ident() for t in threads)
        assert not commands
    finally:
        heartbeat.stop()


def test_preparation_times_out_without_inventing_a_candidate(quick,qt_app):
    r=recorder(quick); r.prepare_seconds=.12
    r.start()
    wait_until(qt_app,lambda:r.phase=='cancelled')
    assert r.result['status']=='cancelled' and r.result['candidate'] is None
    assert quick[1].led_observer is None and not quick[4]


def test_shutdown_cancels_capture_and_never_leaves_a_device_lease(quick,qt_app):
    r=recorder(quick)
    r.start()
    wait_until(qt_app,lambda:r.phase=='prepared')
    quick[1].stop()
    assert quick[1].led_observer is None and r.phase=='cancelled'
    assert not r.timer.isActive() and not r.start() and not quick[4]


def test_scene_selector_opens_and_selects_without_any_network_or_commands(quick):
    panel,_,_,_,commands,_=quick
    panel.bridge.selectDiscoveryScene(1)
    assert panel.bridge.recorder.index==1
    assert panel.bridge.sceneDiscovery['name']=='Dreamland'
    assert not commands


def test_progress_is_persisted_while_waiting_for_manual_scene_selection(quick,qt_app):
    r=recorder(quick)
    r.start()
    wait_until(qt_app,lambda:r.session and len(r.session.frames)>=3)
    result=json.loads(open(r.path,encoding='utf-8').read())
    assert result['status']=='prepared' and '51' in result['changes']
    assert result['candidate'] is None and result['writes_sent']==0
    r.cancel()
    wait_until(qt_app,lambda:r.phase=='cancelled')


def test_partial_capture_failure_saves_evidence_without_replay_candidate(quick,qt_app):
    r=recorder(quick)
    r.reader.capture.side_effect=[frame(),frame(**{'51':RAW}),TimeoutError('synthetic-secret')]
    r.start()
    wait_until(qt_app,lambda:r.phase=='prepared')
    r.conclude()
    wait_until(qt_app,lambda:r.phase=='error')
    assert r.result['status']=='failed' and '51' in r.result['changes']
    assert r.result['candidate'] is None and r.reader.capture.call_count==3
    assert 'synthetic-secret' not in json.dumps(r.result)
    assert quick[1].led_observer is None and not quick[4]


def test_save_failure_releases_lease_and_reports_error_without_new_reads(quick,qt_app,monkeypatch):
    r=recorder(quick)
    monkeypatch.setattr('smart_tray.rgbic_recorder.save_report',Mock(side_effect=OSError('synthetic-secret')))
    r.start()
    wait_until(qt_app,lambda:r.phase=='error')
    assert quick[1].led_observer is None and 'synthetic-secret' not in json.dumps(r.view())
    r.reader.capture.assert_called_once()
    assert not quick[4]


def test_capture_includes_a_final_read_after_the_observation_window(quick,qt_app):
    r=recorder(quick)
    times=[]
    original=r.reader.capture.side_effect
    def capture():
        times.append(time.monotonic())
        return original()
    r.reader.capture.side_effect=capture
    r.start()
    wait_until(qt_app,lambda:r.phase=='prepared')
    start=time.monotonic()
    r.conclude()
    wait_until(qt_app,lambda:r.phase=='saved')
    assert times[-1]-start>=r.observe_seconds
    assert not quick[4]
