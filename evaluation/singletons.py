"""
Global singleton instances for safety, tracking, and mutation control.

These are imported by database.py, main.py, and other modules
to provide centralized state without circular imports.
"""
from .safety import KillSwitch, DrawdownTracker, MutationFreeze

# Global instances — initialized with defaults, configured at startup
kill_switch = KillSwitch()
drawdown_tracker = DrawdownTracker()
mutation_freeze = MutationFreeze()
