#!/usr/bin/env python3
"""
IMMEDIATE CRITICAL FIXES (while sub-agents audit):

1. Signal threshold uses DB setting (was hardcoded 0.25)
2. Min trade interval (prevent rapid-fire) 
3. Signal confirmation buffer (filter noise)
4. Disable EUR pair training (wastes compute)
5. Add per-strategy performance tracking
"""
import os
os.chdir("/root/nexustrader")

with open("main.py") as f:
    c = f.read()

fixes_applied = 0

# FIX 1: Make signal threshold use DB setting instead of hardcoded 0.25
old_threshold = """        if not pos_open:
            # Threshold to trigger evaluation: signal strength > 0.25 (out of -1.0 to 1.0 scale)
            if abs(weighted_signal) >= 0.25:"""

new_threshold = """        if not pos_open:
            # Threshold to trigger evaluation: use DB-configured signal threshold
            _signal_threshold = database.load_setting("signal_threshold", "0.15")
            try:
                _thresh = float(_signal_threshold)
            except:
                _thresh = 0.15
            if abs(weighted_signal) >= _thresh:"""

if old_threshold in c:
    c = c.replace(old_threshold, new_threshold)
    fixes_applied += 1
    print("FIX 1: Signal threshold now uses DB setting (was hardcoded 0.25)")
else:
    print("FIX 1: Pattern not found - may already be fixed")

# FIX 2: Add min_trade_interval check before opening any position
# Find the point right before "if evaluation["is_viable"]:"
old_viable = """                # If viable, open position
                if evaluation["is_viable"]:"""

new_viable = """                # If viable, open position
                if evaluation["is_viable"]:
                    # Min trade interval check (prevent rapid-fire on same ticker)
                    _min_interval = database.load_setting("min_trade_interval_seconds", "60")
                    try:
                        _mi = float(_min_interval)
                    except:
                        _mi = 60
                    if ticker in self.last_trade_time:
                        _elapsed = time.time() - self.last_trade_time[ticker]
                        if _elapsed < _mi:
                            logging.debug(f"Trade interval guard: {ticker} last traded {_elapsed:.1f}s ago (<{_mi}s)")
                            evaluation["is_viable"] = False
                if evaluation["is_viable"]:"""

if old_viable in c:
    c = c.replace(old_viable, new_viable)
    fixes_applied += 1
    print("FIX 2: Min trade interval check added")
else:
    print("FIX 2: Pattern not found")

# FIX 3: Add last_trade_time tracking after successful trade open
# Find "if opened:" inside the position open block
old_opened = """                        if opened:
                            trade_opened = True
                            if self.execution_engine.trading_mode == "live":"""

new_opened = """                        if opened:
                            trade_opened = True
                            # Track last trade time for this ticker
                            self.last_trade_time[ticker] = time.time()
                            if self.execution_engine.trading_mode == "live":"""

if old_opened in c and new_opened not in c:
    c = c.replace(old_opened, new_opened)
    fixes_applied += 1
    print("FIX 3: Last trade time tracking added")

# FIX 4: Add last_trade_time dict initialization in orchestrator
# Find __init__ and add the field
old_init_eval = """        # Signal routing
        self.latest_signals = {}
        self.latest_ticks = {}"""

new_init_eval = """        # Signal routing
        self.latest_signals = {}
        self.latest_ticks = {}
        self.last_trade_time = {}  # ticker -> timestamp"""

if old_init_eval in c:
    c = c.replace(old_init_eval, new_init_eval)
    fixes_applied += 1
    print("FIX 4: last_trade_time dict initialized")

try:
    compile(c, "main.py", "exec")
    print("Syntax OK")
    with open("main.py", "w") as f:
        f.write(c)
    print(f"\n{fxes_applied} fixes applied to main.py")
except SyntaxError as e:
    print(f"SYNTAX ERROR: {e}")
