"""User-scoped Windows startup and per-user single-instance activation."""
import hashlib
import os
from pathlib import Path
import subprocess
import sys
from PySide6.QtCore import QObject, Signal, QLockFile
from PySide6.QtNetwork import QLocalServer, QLocalSocket


def show_interactive_window(widget):
    """Override inherited SW_HIDE for our own explicitly requested GUI only."""
    widget.showNormal()
    widget.raise_()
    widget.activateWindow()
    from PySide6.QtWidgets import QApplication
    if os.name == "nt" and QApplication.platformName() == "windows":
        import ctypes
        from ctypes import wintypes
        user32 = ctypes.WinDLL("user32", use_last_error=True)
        user32.ShowWindow.argtypes = [wintypes.HWND, ctypes.c_int]
        user32.SetForegroundWindow.argtypes = [wintypes.HWND]
        hwnd = int(widget.winId())
        # Qt's isVisible can be true while STARTUPINFO(SW_HIDE) hides the HWND.
        user32.ShowWindow(hwnd, 9)  # SW_RESTORE, after Qt's initial ShowWindow.
        user32.SetForegroundWindow(hwnd)


def startup_command(root):
    if getattr(sys, "frozen", False):
        command = [sys.executable, '--background']
        if hasattr(sys, '_MEIPASS') and not Path(root).resolve().is_relative_to(Path(sys._MEIPASS).resolve()):
            command += ['--config-root', str(Path(root).resolve())]
        return subprocess.list2cmdline(command)
    pythonw = Path(sys.executable).with_name("pythonw.exe")
    if not pythonw.exists():
        raise RuntimeError("Console-free Python unavailable")
    entry = Path(__file__).resolve().parents[2] / 'scripts/run_app.py'
    if (root / 'scripts/run_app.py').exists():
        entry = root / 'scripts/run_app.py'
    command = [str(pythonw), str(entry), '--background']
    if entry.parent.parent.resolve() != root.resolve():
        command += ['--config-root', str(root.resolve())]
    return subprocess.list2cmdline(command)


class Startup:
    key = r"Software\Microsoft\Windows\CurrentVersion\Run"
    name = "SmartTray"

    def enabled(self):
        if os.name != "nt":
            return False
        import winreg
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, self.key) as key:
                value, _ = winreg.QueryValueEx(key, self.name)
                return bool(value)
        except FileNotFoundError:
            return False

    def set_enabled(self, enabled, root):
        import winreg
        with winreg.CreateKey(winreg.HKEY_CURRENT_USER, self.key) as key:
            if enabled:
                winreg.SetValueEx(key, self.name, 0, winreg.REG_SZ, startup_command(root))
            else:
                try:
                    winreg.DeleteValue(key, self.name)
                except FileNotFoundError:
                    pass


class SingleInstance(QObject):
    activated = Signal()

    def __init__(self, directory=None, parent=None):
        super().__init__(parent)
        directory = Path(directory) if directory else Path(os.environ["LOCALAPPDATA"]) / "SmartTray"
        directory.mkdir(parents=True, exist_ok=True)
        self.name = "SmartTray-" + hashlib.sha256(str(directory.resolve()).lower().encode()).hexdigest()[:20]
        self.lock = QLockFile(str(directory / "instance.lock"))
        self.lock.setStaleLockTime(0)  # Qt still checks dead PID ownership.
        self.server = QLocalServer(self)
        self.server.setSocketOptions(QLocalServer.SocketOption.UserAccessOption)
        self.server.newConnection.connect(self._connection)

    def acquire(self):
        if not self.lock.tryLock(0):
            client = QLocalSocket()
            client.connectToServer(self.name)
            if client.waitForConnected(800):
                client.write(b"show")
                client.waitForBytesWritten(800)
                client.disconnectFromServer()
            return False
        QLocalServer.removeServer(self.name)
        if not self.server.listen(self.name):
            self.lock.unlock()
            raise RuntimeError("Local activation unavailable")
        return True

    def _connection(self):
        socket = self.server.nextPendingConnection()
        if socket:
            # The pipe accepts activation only, never device commands/credentials.
            self.activated.emit()
            socket.disconnectFromServer()
            socket.deleteLater()

    def release(self):
        self.server.close()
        self.lock.unlock()
