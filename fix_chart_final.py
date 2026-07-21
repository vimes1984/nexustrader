#!/usr/bin/env python3
"""Fix enhancer.js and index.html inline failsafe chart data formatting."""
import os
os.chdir("/root/nexustrader/dashboard")

# =========== Fix enhancer.js ===========
with open("enhancer.js") as f:
    c = f.read()

# Find and fix the broken volume/color line
old_broken = 'color: "rgba(37,99,235,0.3)" \'rgba(34,197,94,0.4)\' : \'rgba(239,68,68,0.4)\''
new_clean = 'color: "rgba(37,99,235,0.3)"'

if old_broken in c:
    c = c.replace(old_broken, new_clean)
    print("Fixed broken color ternary")
else:
    # Try with different quoting
    for variant in [
        'color: "rgba(37,99,235,0.3)" \\'rgba(34,197,94,0.4)\\' : \\'rgba(239,68,68,0.4)\\'',
        "color: \"rgba(37,99,235,0.3)\" 'rgba(34,197,94,0.4)' : 'rgba(239,68,68,0.4)'",
    ]:
        if variant in c:
            c = c.replace(variant, new_clean)
            print(f"Fixed variant: {variant[:40]}")
            break

# Replace the entire volume line block to be cleaner
old_vol_block = """var tsV = d.time || d.timestamp || 0; if (typeof tsV === "string") tsV = Math.floor(new Date(tsV).getTime() / 1000); volumes.push({
                        time: tsV,
                        value: (d.volume || d.vol || 0) / 10,
                        color: "rgba(37,99,235,0.3)",
                    });
                }
                lineSeries.setData(candles);
                if (volumeSeries) { var v = []; for (var vi=0; vi<volumes.length; vi++) { if (volumes[vi].value > 0) v.push(volumes[vi]); } volumeSeries.setData(v); }
                console.log('[ENHANCER] chart', candles.length, 'candles', ticker, tf);"""

new_vol_block = """}
                lineSeries.setData(candles);
                console.log('[ENHANCER] chart', candles.length, 'candles', ticker, tf);"""

if old_vol_block in c:
    c = c.replace(old_vol_block, new_vol_block)
    print("Fixed volume block")
else:
    print("Volume block not found, searching...")
    idx = c.find("volumes.push")
    if idx >= 0:
        print(f"Found at {idx}: {c[idx:idx+300]}")
        # Find from volumes.push to the setData call
        line_start = c.rfind("\n", 0, idx) + 1
        # Find the end of the volume lines
        setdata_idx = c.find("volumeSeries.setData", idx)
        if setdata_idx >= 0:
            end_vol = c.find("\n", setdata_idx)
            end_vol = c.find("\n", end_vol+1)  # one more line
            print(f"Would replace: {c[line_start:end_vol]}")

with open("enhancer.js", "w") as f:
    f.write(c)
print("Saved enhancer.js")

# =========== Fix index.html ===========
with open("index.html") as f:
    h = f.read()

# Fix the failsafe fetchChartData - replace volume/color line
fs_broken = 'color: "rgba(37,99,235,0.3)"'
# Find the full context to fix properly
idx = h.find(fs_broken)
if idx >= 0:
    # Find end of line
    end_line = h.find("\n", idx)
    line = h[idx:end_line]
    print(f"failsafe color line: {line[:80]}...")

# Fix the whole chart section
# Replace the failsafe fetchChartData completely
old_fs_fetch = """                    candles.push({ time: d.time, open: d.high, low: d.close || d.close || 0 });
                    volumes.push({ time: d.time, value: d.volume || 0, color: d.close >= d.open ? "rgba(34,197,94,0.4)" : "rgba(239,68,68,0.4)" });
                }
                lineSeries.setData(candles);"""

# The failsafe already has lineSeries (we replaced it earlier), just needs data format fix
old_fs_data = """                    var ts = d.time || d.timestamp || 0;
                    if (typeof ts === "string") ts = Math.floor(new Date(ts).getTime() / 1000);
                    candles.push({ time: ts, value: d.close || d.price || 0 });
                    volumes.push({ time: ts, value: (d.volume || d.vol || 0) / 10, color: "rgba(37,99,235,0.3)" });"""

if old_fs_data in h:
    # Remove volumes line
    h = h.replace(old_fs_data, """                    var ts = d.time || d.timestamp || 0;
                    if (typeof ts === "string") ts = Math.floor(new Date(ts).getTime() / 1000);
                    candles.push({ time: ts, value: d.close || d.price || 0 });""")
    print("Fixed failsafe data format")
else:
    print("failsafe data pattern not found")

with open("index.html", "w") as f:
    f.write(h)
print("Saved index.html")
