from PySide6.QtCore import QTimer
from smart_tray.windows import SingleInstance, startup_command


def test_startup_quotes_pythonw_and_root_with_spaces(tmp_path):
    root = tmp_path / "Project With Spaces"
    (root/'scripts').mkdir(parents=True)
    (root/'scripts/run_app.py').write_text('')
    command = startup_command(root)
    assert 'pythonw.exe"' in command
    assert '"' + str(root / "scripts/run_app.py") + '"' in command
    assert command.endswith("--background")


def test_single_instance_rejects_second_and_releases_lock(qt_app, tmp_path):
    first, second = SingleInstance(tmp_path), SingleInstance(tmp_path)
    activated = []
    first.activated.connect(lambda: activated.append(True))
    assert first.acquire()
    assert not second.acquire()
    qt_app.processEvents()
    assert activated == [True]
    first.release()
    assert second.acquire()
    second.release()
