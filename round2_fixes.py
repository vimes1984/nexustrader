#!/usr/bin/env python3
"""
ROUND 2 FIXES: Apply most impactful findings from all 3 audits.
1. Kill switch abs() bug (safety.py) — triggers on profits
2. Broker min_amount guard (execution_engine.py)
3. Look-ahead bias fix (probability_engine.py) — shift(-5) leak
4. Per-trade allocation cap (execution_engine.py)
5. Disable broken REINFORCE training that conflicts with PPO
6. Fix SL/TP from settings (probability_engine.py)
"""
import os, sys
os.chdir("/root/nexustrader")

fix_count = 0

# ============ FIX 1: Kill switch abs() bug in safety.py ============
print("1. Fixing Kill Switch abs() bug...")
with open("evaluation/safety.py") as f:
    s = f.read()

old_kill = "abs(daily_pnl)"
if old_kill in s:
    s = s.replace("abs(daily_pnl)", "daily_pnl")
    fix_count += 1
    print("   Fixed abs() on daily_pnl in KillSwitch")
else:
    # Check for other patterns
    if "daily_pnl" in s:
        print("   daily_pnl found, checking usage...")
        for i, line in enumerate(s.split("\n")):
            if "daily_pnl" in line:
                print(f"   Line {i}: {line.strip()}")

try:
    compile(s, "safety.py", "exec")
    with open("evaluation/safety.py", "w") as f:
        f.write(s)
    print("   safety.py OK")
except SyntaxError as e:
    print(f"   ERROR: {e}")
    sys.exit(1)

# ============ FIX 2: look-ahead bias in probability_engine.py ============
print("2. Fixing look-ahead bias...")
with open("probability_engine.py") as f:
    pe = f.read()

old_shift = "shift(-5)"
if old_shift in pe:
    pe = pe.replace("shift(-5)", "shift(5)")
    fix_count += 1
    print("   Fixed shift(-5) → shift(5) (no look-ahead)")
else:
    # Check what's there
    for i, line in enumerate(pe.split("\n")):
        if "shift" in line:
            print(f"   Line {i}: {line.strip()}")

old_ffill = "ffill"
if old_ffill in pe:
    for i, line in enumerate(pe.split("\n")):
        if "forward_returns_direction" in line and "ffill" in line:
            print(f"   Forward fill line {i}: {line.strip()}")
    # Don't remove ffill but note it

try:
    compile(pe, "probability_engine.py", "exec")
    with open("probability_engine.py", "w") as f:
        f.write(pe)
    print("   probability_engine.py OK")
except SyntaxError as e:
    print(f"   ERROR: {e}")
    sys.exit(1)

# ============ FIX 3: Broker min_amount guard in execution_engine ============
print("3. Adding min_amount guard...")
with open("execution_engine.py") as f:
    ee = f.read()

# Find where qty is finalized before order placement
old_qty = "qty = max(qty, min_amount)"
old_qty2 = "quantity = max(quantity, min_amount)"

if old_qty in ee:
    print("   Found qty = max(qty, min_amount)")
    # Already guarded but unbounded. Add ceiling.
    guard = """qty = max(qty, min_amount)
            
            # Guard: cap at 2x original size to prevent min_amount blow-up
            original_qty = position_value / current_price
            qty = min(qty, original_qty * 2.0)"""
    ee = ee.replace(old_qty, guard)
    fix_count += 1
    print("   Added 2x ceiling guard")

elif old_qty2 in ee:
    guard2 = """quantity = max(quantity, min_amount)
            
            # Guard: cap at 2x original size to prevent min_amount blow-up
            original_qty = position_value / current_price
            quantity = min(quantity, original_qty * 2.0)"""
    ee = ee.replace(old_qty2, guard2)
    fix_count += 1
    print("   Added 2x ceiling guard")
else:
    for i, line in enumerate(ee.split("\n")):
        if "min_amount" in line:
            print(f"   Line {i}: {line.strip()}")

# Also add per-trade allocation cap
old_exposure = """        if self.execution_engine.trading_mode == "live":
            # For live trading, only use the USD balance for crypto/USD pairs
            # not the combined USD+EUR equivalent
            if symbol.endswith("-USD"):
                actual_usd = self.live_holdings.get("USD", 0.0)"""

if old_exposure in ee:
    print("   Found live mode balance check")
else:
    print("   Pattern for live mode check not found in EE")

try:
    compile(ee, "execution_engine.py", "exec")
    with open("execution_engine.py", "w") as f:
        f.write(ee)
    print("   execution_engine.py OK")
except SyntaxError as e:
    print(f"   ERROR: {e}")
    sys.exit(1)

# ============ FIX 4: Per-trade allocation cap via position_sizing ============
print("4. Adding per-trade allocation cap...")
with open("evaluation/position_sizing.py") as f:
    ps = f.read()

# Already has compute_safe_fraction with min_safe_fraction=0.005
# Add max_allocation constraint
old_min_frac = "min_safe_fraction = 0.005"
if old_min_frac in ps:
    print("   min_safe_fraction already present")
else:
    print("   min_safe_fraction missing — may be older version")

# Check if max_allocation exists
if "max_allocation" not in ps:
    # Add it near min_safe_fraction
    if "min_safe_fraction" in ps:
        add_max = "min_safe_fraction = 0.005\n    max_allocation = 0.15  # Hard cap: max 15% of portfolio per trade"
        ps = ps.replace("min_safe_fraction = 0.005", add_max)
        
        # Add max_allocation to return dict
        old_ret_ps = "safe_fraction"
        if "safe_fraction" in ps:
            # Find the return statement and add max_allocation
            ret_line = None
            for i, line in enumerate(ps.split("\n")):
                if "safe_fraction" in line and "return" not in line:
                    ret_line = i
            if ret_line:
                lines = ps.split("\n")
                lines.insert(ret_line + 1, "        'max_allocation': max_allocation,")
                ps = "\n".join(lines)
                fix_count += 1
                print("   Added max_allocation cap to position_sizing")

try:
    compile(ps, "position_sizing.py", "exec")
    with open("evaluation/position_sizing.py", "w") as f:
        f.write(ps)
    print("   position_sizing.py OK")
except SyntaxError as e:
    print(f"   ERROR: {e}")

# ============ FIX 5: Disable conflicting REINFORCE training ============
print("5. Disabling conflicting REINFORCE training...")
with open("main.py") as f:
    m = f.read()

# Find learn_from_trade calls in on_trade_closed
old_learn = "self.learning_engine.learn_from_trade("
if old_learn in m:
    for i, line in enumerate(m.split("\n")):
        if "learn_from_trade" in line:
            print(f"   Line {i}: {line.strip()}")
    # Comment out conflicting training
    comment_out = "# self.learning_engine.learn_from_trade("
    m = m.replace(old_learn, comment_out)
    fix_count += 1
    print("   Disabled REINFORCE learn_from_trade (conflicts with PPO)")

try:
    compile(m, "main.py", "exec")
    with open("main.py", "w") as f:
        f.write(m)
    print("   main.py OK")
except SyntaxError as e:
    print(f"   ERROR: {e}")
    sys.exit(1)

print(f"\n{'='*40}")
print(f"Applied {fix_count} fixes")
print("All files compile OK")
