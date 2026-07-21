#!/usr/bin/env python3
"""Fix equity calculation: remove cross-asset price fallback that inflates equity."""
import os, sys
os.chdir("/root/nexustrader")

with open("execution_engine.py") as f:
    ee = f.read()

# The offending code: fallback keys include BTC-USD, ETH-USD, XRP-USD
# which assigns BTC price to SOL, XRP, AVAX etc.
old_fallback = """                    # Try current price inputs (e.g. from websocket ticks / base assets list)
                    for key in [f"{norm_asset}-USD", f"{norm_asset}/USD", f"{asset}-USD", f"{asset}/USD", f"BTC-USD", f"ETH-USD", f"XRP-USD"]:
                        if key in current_prices and current_prices[key] is not None:
                            price = float(current_prices[key])
                            break
                    if price is None or price == 0.0:
                        price = float(last_prices.get(norm_asset, last_prices.get(asset, 0.0)))"""

new_fallback = """                    # Try current price inputs for this specific asset only
                    for key in [f"{norm_asset}-USD", f"{norm_asset}/USD", f"{asset}-USD", f"{asset}/USD"]:
                        if key in current_prices and current_prices[key] is not None and current_prices[key] > 0:
                            price = float(current_prices[key])
                            break
                    # Fallback to last known price from DB (never cross-asset)
                    if price is None or price <= 0.0:
                        db_price = last_prices.get(norm_asset, last_prices.get(asset, 0.0))
                        price = float(db_price) if db_price else 0.0"""

if old_fallback in ee:
    ee = ee.replace(old_fallback, new_fallback)
    compile(ee, "execution_engine.py", "exec")
    with open("execution_engine.py", "w") as f:
        f.write(ee)
    print("FIXED: Removed cross-asset BTC/ETH/XRP fallback. Equity will use actual prices or last_known_prices.")
else:
    print("Pattern not found — equity code may have changed. Checking...")
    import re
    matches = re.findall(r"BTC-USD.*ETH-USD.*XRP-USD", ee)
    if matches:
        print(f"Found variant: {matches[0][:80]}...")
    else:
        print("No cross-asset fallback found")
