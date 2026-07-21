#!/usr/bin/env python3
"""Fix enhancer.js and index.html chart data formatting - clean version."""
import os
os.chdir("/root/nexustrader/dashboard")

# =========== Fix enhancer.js ===========
with open("enhancer.js") as f:
    c = f.read()

# Just find the broken line and fix it directly
idx = c.find('"rgba(37,99,235,0.3)"')
if idx >= 0:
    # Find from here to end of line
    endline = c.find("\n", idx)
    line = c[idx:endline]
    print(f"Found problematic line: {line[:80]}")
    
    # Replace the whole broken object entry
    obj_start = c.rfind("color", idx - 50, idx)
    if obj_start >= 0:
        obj_end = c.find(",", obj_start)
        if obj_end >= 0 and obj_end < obj_start + 100:
            replacement = 'color: "rgba(37,99,235,0.3)"'
            c = c[:obj_start] + replacement + c[endline:]
            print("Fixed broken color line via direct replacement")
        else:
            print("Couldn't find end of color line")
    else:
        print("Couldn't find color start")
else:
    print("rgba(37,99,235,0.3) not found in enhancer.js")

# Now also drop the volumes.push block and volumeSeries.setData
old_volume_section = """var tsV = d.time || d.timestamp || 0; if (typeof tsV === "string") tsV = Math.floor(new Date(tsV).getTime() / 1000); volumes.push({"""
if old_volume_section in c:
    # Find the end of this section
    vstart = c.find(old_volume_section)
    vclose = c.find("volumeSeries.setData", vstart)
    if vclose >= 0:
        vend = c.find("\n", vclose)
        vend = c.find("\n", vend + 1)
        c = c[:vstart] + c[vend+1:]
        print("Removed volumes.push section")
else:
    print("No volumes.push section found, checking for alternative...")
    # Maybe already partially replaced
    idx2 = c.find("volumes.push")
    if idx2 >= 0:
        print(f"Found volumes.push at {idx2}")
        print(f"Context: {c[idx2:idx2+100]}")

with open("enhancer.js", "w") as f:
    f.write(c)
print("Saved enhancer.js")

# =========== Fix index.html ===========
with open("index.html") as f:
    h = f.read()

# Fix the failsafe fetchChartData
old_fs_line = 'volumes.push({ time: ts, value: (d.volume || d.vol || 0) / 10, color: "rgba(37,99,235,0.3)" });'
if old_fs_line in h:
    h = h.replace(old_fs_line, "")
    print("Removed failsafe volumes line")

# Also check for any remnants
# Remove the newline + line if it was removed
h = h.replace("                    \n", "")

with open("index.html", "w") as f:
    f.write(h)
print("Saved index.html")
