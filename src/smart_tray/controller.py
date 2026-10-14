"""GUI-owned state, serialized network workers and read-only reconnection."""
from PySide6.QtCore import QObject, QRunnable, QThreadPool, Signal, Slot, QTimer, Qt
from .adapters import DeviceState
from .ui_diagnostics import record


class WorkerSignals(QObject):
    completed = Signal(str, object)


class Worker(QRunnable):
    def __init__(self, role, operation):
        super().__init__()
        self.role, self.operation = role, operation
        self.signals = WorkerSignals()

    def run(self):
        try:
            state = self.operation()
        except Exception as error:
            record("worker_error", role=self.role, error_type=type(error).__name__)
            state = DeviceState("unknown", {}, "Operação indisponível")
        self.signals.completed.emit(self.role, state)


class Controller(QObject):
    changed = Signal()

    def __init__(self, adapters, parent=None, interval=15000):
        super().__init__(parent)
        self.adapters = adapters
        self.states = {role: DeviceState() for role in adapters}
        if not getattr(adapters["elgin"], "capabilities", {}):
            self.states["elgin"] = DeviceState("pending", {}, "Aguardando configuração")
        self.busy, self.workers = set(), {}
        self.writing, self.stopping = False, False
        self.write_role = None
        self.pool = QThreadPool(self)
        self.pool.setMaxThreadCount(3)  # One operation per device; writes remain globally exclusive.
        self.timer = QTimer(self)
        self.timer.setInterval(interval)
        self.timer.timeout.connect(self.refresh)

    def start(self):
        self.refresh()
        self.timer.start()

    @Slot()
    def refresh(self):
        if self.stopping or self.writing:
            return
        for role in self.adapters:
            if (role == "elgin" and not self.elgin_capabilities()) or role in self.busy:
                continue
            self._submit(role, self.adapters[role].read)

    def _submit(self, role, operation):
        self.busy.add(role)
        worker = Worker(role, operation)
        worker.signals.completed.connect(self._completed, Qt.ConnectionType.QueuedConnection)
        self.workers[role] = worker
        self.changed.emit()
        self.pool.start(worker)

    def can_write(self, role, dp):
        state = self.states.get(role)
        return bool(not self.stopping and not self.writing and role not in self.busy and state
                    and state.connection == "online" and type(state.values.get(dp)) is bool
                    and dp in self.adapters[role].channels)

    def toggle(self, role, dp):
        if not self.can_write(role, dp):
            return False
        before = self.states[role].values[dp]
        self.writing = True
        self.write_role = role
        record("power_dispatched", role=role, dp=dp)
        self._submit(role, lambda: self.adapters[role].write(dp, before, not before))
        return True

    def elgin_capabilities(self):
        return {name: spec for name, spec in getattr(self.adapters["elgin"], "capabilities", {}).items()
                if spec.get("validated") is True}

    def request_elgin(self, name, value):
        spec = self.elgin_capabilities().get(name)
        state = self.states["elgin"]
        if not spec or self.stopping or self.writing or "elgin" in self.busy or state.connection != "online":
            return False
        known = state.values.get(name)
        if known is None or value == known:
            return False
        if any(state.values.get(key) != expected for key, expected in spec.get("requires", {}).items()):
            return False
        kind = spec.get("kind")
        valid = ((kind == "boolean" and type(value) is bool)
                 or (kind == "number" and type(value) in (int, float)
                     and spec["min"] <= value <= spec["max"]
                     and (value - spec["min"]) % spec.get("step", 1) == 0)
                 or (kind == "choice" and value in spec.get("options", {})))
        if not valid:
            return False
        self.writing = True
        self.write_role = "elgin"
        adapter = self.adapters["elgin"]
        operation = (lambda: adapter.command_from_state(name, known, value)) if hasattr(adapter, "command_from_state") else (lambda: adapter.command(name, value))
        self._submit("elgin", operation)
        return True

    @Slot(str, object)
    def _completed(self, role, state):
        self.states[role] = state
        self.busy.discard(role)
        self.workers.pop(role, None)
        if self.write_role == role or self.writing and not self.busy:
            self.writing = False
            self.write_role = None
        record("worker_completed", role=role, connection=state.connection)
        self.changed.emit()

    def stop(self):
        self.stopping = True
        self.timer.stop()
        self.pool.clear()  # Cancel queued operations; never replay on restart.
        self.changed.emit()
