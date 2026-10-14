"""Product flows with actual Qt clicks, mocked LAN and no credential access."""
from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QMessageBox
from smart_tray.adapters import DeviceState
from smart_tray.beta import BetaSettings
from test_gui_responsiveness import gui, click
from test_interface import wait_until


def test_inline_beta_release_cancel_and_accept_never_write(gui, qt_app):
    panel, controller, adapters = gui
    controller.settings.enabled = False
    controller.changed.emit()
    assert panel.unlock_beta.isVisible() and not panel.colour_button.isEnabled()
    click(panel.unlock_beta)
    click(panel.dialogs['confirmation'].button(QMessageBox.StandardButton.No))
    assert not controller.settings.enabled
    click(panel.unlock_beta)
    click(panel.dialogs['confirmation'].button(QMessageBox.StandardButton.Yes))
    assert controller.settings.enabled and BetaSettings(controller.settings.directory).enabled
    assert panel.colour_button.isEnabled()
    assert not panel.unlock_beta.isVisible()
    for role in ('elgin', 'led'):
        adapters[role].execute.assert_not_called()


def test_scene_to_colour_is_explicit_single_dps_before_picker(gui, qt_app):
    panel, controller, adapters = gui
    controller.states['led'] = DeviceState('online', {20: True, 'mode': 'scene', 'colour': '000003e803e8', 'brightness': 100})
    controller.changed.emit()
    assert panel.fixed_colour.isVisible() and panel.fixed_colour.isEnabled()
    assert not panel.colour_button.isEnabled() and not panel.brightness.isEnabled()
    click(panel.fixed_colour)
    assert '{"21": "colour"}' in panel.dialogs['confirmation'].text()
    adapters['led'].execute.assert_not_called()
    click(panel.dialogs['confirmation'].button(QMessageBox.StandardButton.Yes))
    wait_until(qt_app, lambda: not controller.writing)
    adapters['led'].execute.assert_called_once()
    assert adapters['led'].execute.call_args.args[0::2] == ('mode', 'colour')
    assert panel.colour_button.isEnabled() and panel.brightness.isEnabled()
    adapters['elgin'].execute.assert_not_called()
    adapters['novadigital'].write.assert_not_called()


def test_elgin_readonly_mode_is_a_readout_not_dropdown(gui):
    panel, controller, _ = gui
    controller.settings.enabled = False
    controller.changed.emit()
    assert not panel.elgin.mode.isVisible()
    assert panel.mode_readout.isVisible() and 'Resfriar' in panel.mode_readout.text()
    assert 'Somente leitura' in panel.mode_readout.text()
    assert panel.elgin.plus.isEnabled() and panel.elgin.fan.isEnabled()
    controller.settings.enabled = True
    controller.changed.emit()
    assert panel.elgin.mode.isVisible() and not panel.mode_readout.isVisible()


def test_advanced_release_available_without_hidden_settings(gui):
    panel, controller, adapters = gui
    controller.settings.enabled = False
    controller.changed.emit()
    dialog = panel.advanced('led')
    release = dialog.findChild(__import__('PySide6.QtWidgets', fromlist=['QPushButton']).QPushButton, 'betaUnlock')
    assert release.isVisible() and release.isEnabled()
    assert not dialog.controls['colour'].isEnabled()
    adapters['led'].execute.assert_not_called()


def test_effects_navigation_explains_real_limits_without_commands(gui, qt_app):
    panel, _, adapters = gui
    click(panel.effects)
    qt_app.processEvents()
    dialog = panel.dialogs['advanced_led']
    assert set(dialog.sections) == {'COR', 'BRILHO', 'FAVORITOS', 'CENAS / EFEITOS', 'RECURSOS RGBIC', 'MÚSICA', 'OUTROS RECURSOS'}
    target = dialog.sections['CENAS / EFEITOS']
    assert dialog.scroll.viewport().rect().contains(target.mapTo(dialog.scroll.viewport(), target.rect().center()))
    assert panel.advanced('led', 'COR') is dialog
    adapters['led'].execute.assert_not_called()


def test_offline_and_pending_are_visible_and_prevent_actions(gui):
    panel, controller, adapters = gui
    controller.states['led'] = DeviceState('offline', {})
    controller.changed.emit()
    assert 'Erro' in panel.led_controls_status.text()
    assert not panel.colour_button.isEnabled() and not panel.led_mode.isEnabled()
    controller.busy.add('led')
    controller.changed.emit()
    assert 'Aguardando' in panel.led_controls_status.text()
    assert not panel.brightness.isEnabled()
    controller.busy.discard('led')
    adapters['led'].execute.assert_not_called()


def test_main_led_selector_keeps_popup_model_during_refresh(gui, qt_app):
    panel, controller, adapters = gui
    panel.led_mode.showPopup()
    qt_app.processEvents()
    model = panel.led_mode.model()
    index = model.index(panel.led_mode.findData('scene'), 0)
    controller.changed.emit()
    assert panel.led_mode.view().isVisible() and index.isValid()
    assert panel.led_mode.model() is model
    panel.led_mode.hidePopup()
    adapters['led'].execute.assert_not_called()


def test_advanced_brightness_pending_value_survives_read_refresh(gui):
    panel, controller, adapters = gui
    dialog = panel.advanced('led')
    slider = dialog.controls['brightness']
    slider.setValue(42)
    controller.changed.emit()
    assert slider.value() == 42
    dialog.close()  # Cancels the pending debounce; does not dispatch a command.
    adapters['led'].execute.assert_not_called()
