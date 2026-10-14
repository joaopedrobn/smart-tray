"""Adapters for intentional target selection; no animation generates writes."""
from .beta import BetaAdapter, load_beta_adapters


class InteractiveAdapter(BetaAdapter):
    def temperature_change_allowed(self, before, target):
        # The slider selects one exact setpoint, never a loop of +/- commands.
        # DP2, its scale, integral step and physical 16..32 range are identified.
        # All inherited fresh-state/power/mode/timeout/no-retry guards still run.
        return type(target) in (int, float) and float(target).is_integer() and 16 <= target <= 32


def load_interactive_adapters(root):
    adapters = load_beta_adapters(root)
    for role in ('elgin', 'led'):
        adapter = adapters[role]
        if isinstance(adapter, BetaAdapter):
            adapters[role] = InteractiveAdapter(adapter.base, root)
    return adapters
