"""Windows tray entry; no console and no device control at launch."""
import argparse
import logging
from pathlib import Path
import sys

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication, QSystemTrayIcon, QMenu, QMessageBox
from .adapters import load_adapters
from .controller import Controller
from .ui import Panel, configure_style, icon
from .windows import SingleInstance, Startup


class TrayApplication:
    def __init__(self, app, root, controller, instance, panel_factory=Panel):
        self.app, self.root, self.controller, self.instance = app, root, controller, instance
        self.startup = Startup()
        self.panel = panel_factory(controller)
        self.tray = QSystemTrayIcon(icon(), app)
        self.tray.setToolTip("Smart Tray · controle local")
        self.menu = QMenu()
        self.menu.addAction("Abrir Smart Tray", self.show)
        self.menu.addAction("Atualizar estados", controller.refresh)
        self.menu.addSeparator()
        self.startup_action = self.menu.addAction("Iniciar com Windows")
        self.startup_action.setCheckable(True)
        self.startup_action.setChecked(self.startup.enabled())
        self.startup_action.triggered.connect(self.configure_startup)
        if not getattr(sys, 'frozen', False):
            self.menu.addAction("Guia de integração Elgin", self.open_guide)
        if hasattr(self.panel, "settings_dialog"):
            self.menu.addAction("Configurações / Sobre / Histórico", self.open_settings)
        if hasattr(self.panel, "reset_position"):
            self.menu.addAction("Restaurar posição padrão", self.panel.reset_position)
        self.menu.addSeparator()
        self.menu.addAction("Sair do Smart Tray", self.quit)
        self.menu.aboutToShow.connect(lambda: setattr(self.panel, "menu_visible", True))
        self.menu.aboutToHide.connect(lambda: setattr(self.panel, "menu_visible", False))
        self.tray.setContextMenu(self.menu)
        self.tray.activated.connect(self.activate)
        self.panel.preferences.connect(self.open_settings if hasattr(self.panel, "settings_dialog") else lambda: self.menu.popup(self.panel.mapToGlobal(self.panel.rect().topRight())))
        self.menu.aboutToShow.connect(lambda: self.startup_action.setChecked(self.startup.enabled()))
        instance.activated.connect(self.show)
        self.exit_timer = QTimer(app)
        self.exit_timer.setInterval(100)
        self.exit_timer.timeout.connect(self._finish_quit)
        self.tray.show()

    def show(self):
        if not self.controller.stopping:
            self.panel.show_at_tray(self.tray.geometry())

    def open_settings(self):
        self.show()
        self.panel.settings_dialog()

    def activate(self, reason):
        if reason == QSystemTrayIcon.ActivationReason.Trigger:
            self.show()

    def configure_startup(self, enabled):
        try:
            self.startup.set_enabled(enabled, self.root)
        except Exception:
            self.startup_action.setChecked(self.startup.enabled())
            self.tray.showMessage("Smart Tray", "Não foi possível alterar a inicialização com Windows.")

    def open_guide(self):
        from PySide6.QtCore import QUrl
        from PySide6.QtGui import QDesktopServices
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(self.root / "diagnostics/elgin-integration.md")))

    def quit(self):
        self.controller.stop()
        self.panel.hide()
        self.menu.setEnabled(False)
        self.tray.setToolTip("Smart Tray · encerrando comunicação…")
        self.exit_timer.start()

    def _finish_quit(self):
        if self.controller.pool.activeThreadCount() == 0:
            self.exit_timer.stop()
            self.tray.hide()
            self.instance.release()
            self.app.quit()


def main(root=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--background", action="store_true")
    parser.add_argument('--config-root', type=Path, help='Private directory containing diagnostics/ and profiles/')
    parser.add_argument("--read-only-smoke", action="store_true", help="Bounded native check; all writes blocked")
    parser.add_argument("--interaction-smoke", action="store_true", help="Native clicks with simulated devices; no LAN or credentials")
    parser.add_argument("--qt-interaction-smoke", action="store_true", help="Qt window interaction with simulated devices; no LAN or credentials")
    args = parser.parse_args()
    root = (Path(sys._MEIPASS) / "data" if getattr(sys, "frozen", False) else
            Path(root) if root else Path(__file__).resolve().parents[2])
    if args.config_root:
        root = args.config_root.resolve()
    # Library debug output must never expose authentication material.
    logging.disable(logging.CRITICAL)
    app = QApplication(sys.argv[:1])
    app.setApplicationName("Smart Tray")
    app.setOrganizationName("SmartTray")
    app.setQuitOnLastWindowClosed(False)
    configure_style(app)
    from .ui_diagnostics import install_exception_hook
    install_exception_hook()
    app.setWindowIcon(icon())
    instance = SingleInstance()
    if not instance.acquire():
        return 0
    try:
        if args.interaction_smoke or args.qt_interaction_smoke:
            from .quick_smoke import run
            from os import environ
            demo_root = Path(sys._MEIPASS) / 'demo-data' if getattr(sys, 'frozen', False) else Path(__file__).resolve().parents[2] / 'tests/fixtures/config'
            return run(app, demo_root, Path(environ["LOCALAPPDATA"]) / "SmartTray/gui-interaction-smoke.json", native_input=not args.qt_interaction_smoke)
        from .beta import BetaSettings, VERSION
        from .direct_controller import DirectController
        from .quick_panel import QuickPanel
        from .interactive_adapters import load_interactive_adapters
        adapters = load_interactive_adapters(root)
        settings = BetaSettings()
        if args.read_only_smoke:
            def prohibit(*args, **kwargs):
                raise RuntimeError("Read-only smoke: write blocked")
            for adapter in adapters.values():
                for method in ("write", "command", "command_from_state", "execute"):
                    if hasattr(adapter, method):
                        setattr(adapter, method, prohibit)
                base = getattr(adapter, "base", adapter)
                original_factory = getattr(base, "factory", None)
                if original_factory:
                    def guarded_factory(*a, factory=original_factory, **kw):
                        device = factory(*a, **kw)
                        # Tuya 3.4/3.5 authentication also uses quick transport.
                        # Block CONTROL payloads, preserving session handshakes.
                        from tinytuya.core import command_types as CT
                        generate = device.generate_payload
                        def guarded_payload(command, *a, **kw):
                            if command in {CT.CONTROL, getattr(CT, "CONTROL_NEW", 13)}:
                                return prohibit()
                            return generate(command, *a, **kw)
                        device.generate_payload = guarded_payload
                        return device
                    base.factory = guarded_factory
        controller = DirectController(adapters, settings)
        tray_app = TrayApplication(app, root, controller, instance, panel_factory=lambda c: QuickPanel(c, root))
        tray_app.tray.setToolTip("Smart Tray " + VERSION)
        controller.start()
        if args.read_only_smoke:
            import json
            timer = QTimer(app)
            timer.setInterval(100)
            def capture():
                if controller.busy:
                    return
                timer.stop()
                tray_app.show()
                tray_app.panel.animation.stop()
                tray_app.panel.setWindowOpacity(1)
                QTimer.singleShot(200, save_capture)

            def save_capture():
                tray_app.panel.grab().save(str(settings.directory / "beta-preview.png"))
                result = {"version": VERSION, "writes": 0, "frozen": bool(getattr(sys, "frozen", False)),
                    "states": {role: {"connection": state.connection, "values": state.values} for role, state in controller.states.items()},
                    "adapters": {role: type(adapter).__name__ for role, adapter in adapters.items()}}
                (settings.directory / "beta-smoke.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
                tray_app.quit()
            timer.timeout.connect(capture)
            timer.start()
            QTimer.singleShot(30000, tray_app.quit)
        if not args.background or not QSystemTrayIcon.isSystemTrayAvailable():
            QTimer.singleShot(0, tray_app.show)
        return app.exec()
    except Exception:
        QMessageBox.critical(None, "Smart Tray", "Não foi possível iniciar. Confira o ambiente e os perfis locais.")
        return 1
    finally:
        instance.release()


if __name__ == "__main__":
    raise SystemExit(main())
