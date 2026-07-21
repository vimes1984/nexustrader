#!/usr/bin/env python3
"""Add portfolio-level risk monitoring: max open positions + concentration limits.
Matches actual execution_engine.py structure (open_position at L354, active_positions dict)."""
import os, sys
os.chdir("/root/nexustrader")

with open("execution_engine.py") as f:
    ee = f.read()

changes = 0

# FIX 1: Add max_open_positions to __init__
old_init = "        self.active_positions = {}  # symbol -> position dict"
new_init = """        self.active_positions = {}  # symbol -> position dict
        self.max_open_positions = 3  # Hard limit: max concurrent positions
        self.max_concentration = 0.40  # Max portfolio % in a single ticker
        self.max_total_exposure = 0.60  # Max % of portfolio in all open positions"""
if old_init in ee:
    ee = ee.replace(old_init, new_init)
    changes += 1
    print("FIX 1: Added max_open_positions=3, max_concentration=0.40, max_total_exposure=0.60")
else:
    print("ERROR: init pattern not found")

# FIX 2: Add position count and concentration checks in open_position()
old_cooldown = """        if symbol in self.active_positions or symbol in self.pending_limit_orders:
            logging.warning(f"Position or pending order already exists for {symbol}. Skipping.")
            return False"""

new_cooldown = """        # Portfolio-level risk checks
        if len(self.active_positions) >= self.max_open_positions:
            logging.warning(f"[PORTFOLIO RISK] Max open positions ({self.max_open_positions}) reached. Skipping {symbol}.")
            return False
        
        # Concentration limit: prevent too much capital in one position
        total_equity = self.get_equity()
        kf = evaluation.get("kelly_fraction", 0.05)
        position_value_est = self.balance * kf
        existing_exposure = 0.0
        for pos in self.active_positions.values():
            existing_exposure += pos.get('quantity', 0) * pos.get('entry_price', 0)
        if total_equity > 0 and position_value_est > 0:
            new_total_exposure = (existing_exposure + position_value_est) / total_equity
            if new_total_exposure > self.max_total_exposure:
                logging.warning(f"[PORTFOLIO RISK] Total exposure {new_total_exposure:.1%} would exceed {self.max_total_exposure:.1%}. Skipping {symbol}.")
                return False
            single_exposure = position_value_est / total_equity
            if single_exposure > self.max_concentration:
                logging.warning(f"[PORTFOLIO RISK] Single position {single_exposure:.1%} exceeds {self.max_concentration:.1%}. Skipping {symbol}.")
                return False
        
        if symbol in self.active_positions or symbol in self.pending_limit_orders:
            logging.warning(f"Position or pending order already exists for {symbol}. Skipping.")
            return False"""

if old_cooldown in ee:
    ee = ee.replace(old_cooldown, new_cooldown)
    changes += 1
    print("FIX 2: Added max_open_positions + concentration + total_exposure checks")
else:
    print("ERROR: cooldown pattern not found")

# FIX 3: Load max_open_positions from DB (find load_setting calls in __init__)
old_db = "        self.transaction_fee_rate = float(database.load_setting(\"transaction_fee_rate\", \"0.0026\"))"
new_db = """        self.max_open_positions = int(database.load_setting("max_open_positions", "3"))
        self.transaction_fee_rate = float(database.load_setting("transaction_fee_rate", "0.0026"))"""
if old_db in ee:
    ee = ee.replace(old_db, new_db)
    changes += 1
    print("FIX 3: max_open_positions loaded from DB")
else:
    # Try alternative patterns
    for pattern in ["transaction_fee_rate = float(database.load_setting", "load_setting.*transaction_fee"]:
        if pattern in ee:
            print(f"  Found transaction_fee_rate pattern, trying to insert before it")
            break
    else:
        print("  No DB load pattern found for max_open_positions")

try:
    compile(ee, "execution_engine.py", "exec")
    with open("execution_engine.py", "w") as f:
        f.write(ee)
    print(f"\nApplied {changes} fixes to execution_engine.py - syntax OK")
except SyntaxError as e:
    print(f"SYNTAX ERROR: {e}")
    # Revert
    os.system("cd /root/nexustrader && git checkout execution_engine.py 2>/dev/null")
    sys.exit(1)
