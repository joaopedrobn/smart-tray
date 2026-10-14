"""GUI action gates; startup and polling are always read-only."""
from PySide6.QtCore import Signal
from .controller import Controller
from .beta import BetaAdapter
from .ui_diagnostics import record


class BetaController(Controller):
    action_finished = Signal(str, object)

    def __init__(self, adapters, settings, *args, **kwargs):
        self.settings = settings
        self.pending_action = None
        super().__init__(adapters, *args, **kwargs)

    def capabilities_for(self, role):
        adapter = self.adapters[role]
        if not isinstance(adapter, BetaAdapter):
            return super().elgin_capabilities() if role == "elgin" else {}
        result = {}
        for name, spec in adapter.capabilities.items():
            if self.settings.enabled:
                result[name] = dict(spec)
                if spec.get("kind") == "choice":
                    options = {v: title + (" · β" if not adapter.is_validated(name, v) else "")
                               for v, title in spec["options"].items()}
                    result[name].update(options=options, observed_options=options)
            elif spec.get("validated"):
                result[name] = spec
            elif spec.get("validated_values"):
                result[name] = {**spec, "validated": True,
                    "options": {v: spec["options"][v] for v in spec["validated_values"]},
                    "observed_options": spec["options"]}
        return result

    def elgin_capabilities(self):
        return self.capabilities_for("elgin")

    def request_elgin(self, name, value):
        return self.request_beta("elgin", name, value)

    def request_beta(self, role, name, value, *, approved=False):
        adapter = self.adapters[role]
        if not isinstance(adapter, BetaAdapter):
            return super().request_elgin(name, value) if role == "elgin" else False
        state = self.states[role]
        spec = self.capabilities_for(role).get(name)
        if (not spec or self.stopping or self.writing or role in self.busy
                or state.connection != "online" or state.values.get(name) is None or state.values.get(name) == value):
            return False
        experimental = not adapter.is_validated(name, value)
        if experimental and (not self.settings.enabled or approved is not True):
            return False
        try:
            adapter.validate(name, value)
            adapter.proposed(name, value, state)
        except (ValueError, TypeError):
            return False
        if any(state.values.get(key) != expected for key, expected in spec.get("requires", {}).items()):
            return False
        self.writing = True
        self.write_role = role
        self.pending_action = role
        record("beta_dispatched", role=role, function=name)
        self._submit(role, lambda: adapter.execute(name, state, value, experimental_approved=approved))
        return True

    def _completed(self, role, state):
        super()._completed(role, state)
        if self.pending_action == role:
            self.pending_action = None
            adapter = self.adapters[role]
            if adapter.last_result:
                self.action_finished.emit(role, adapter.last_result)
