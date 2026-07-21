#!/usr/bin/env python3
"""Fix broken chart data formatting in enhancer.js."""
import os
os.chdir("/root/nexustrader/dashboard")

with open("enhancer.js") as f:
    c = f.read()

# Fix the broken volume line
old_vol_broken = """                        color: "rgba(37,99,235,0.3)" \'rgba(34,197,94,0.4)\' : \'rgba(239,68,68,0.4)\',"""

# The actual text might differ with escaped quotes
# Let me find it
idx = c.find("color: \"rgba(37,99,235,0.3)\"")
if idx >= 0:
    print(f"Found broken color at {idx}")
    # Find the end of this object - look for the closing brace
    end_idx = c.find("},", idx)
    replacement = '                        color: "rgba(37,99,235,0.3)",'
    c = c[:idx] + replacement + c[idx+len(old_vol_broken):]
    print("Fixed broken color line")
else:
    print("Trying different match...")
    # Try with escaped quotes
    idx = c.find('color: "rgba(37,99,235,0.3)" ')
    if idx >= 0:
        end_idx = c.find("}", idx)
        c = c[:idx] + '                        color: "rgba(37,99,235,0.3)"' + c[end_idx:]
        print("Fixed (approach 2)")
    else:
        print("Could not find broken line, checking context:")
        idx2 = c.find("volumeSeries.setData(")
        if idx2 >= 0:
            print(c[idx2-150:idx2+30])

# Also fix the volumeSeries setData to not filter (volume data is all zeros anyway)
# Drop volume series entirely since there is no volume data
# Instead, just keep the line series only

# Replace the entire volume section to be cleaner
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
                // Volume data not available from this endpoint
                console.log('[ENHANCER] chart', candles.length, 'candles', ticker, tf);"""

if old_vol_block in c:
    c = c.replace(old_vol_block, new_vol_block)
    print("Fixed volume block")
else:
    print("Volume block pattern mismatch, dumping context...")
    idx = c.find("volumes.push")
    if idx >= 0:
        print(c[idx:idx+400])

with open("enhancer.js", "w") as f:
    f.write(c)
print("Saved")
