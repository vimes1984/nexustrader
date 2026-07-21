#!/usr/bin/env python3
"""Clean duplicate pollPositions and renderOpenPositions from enhancer.js."""
import os
os.chdir("/root/nexustrader/dashboard")

with open("enhancer.js") as f:
    lines = f.readlines()

# Find all function pollPositions and window.renderOpenPositions lines
poll_lines = []
render_lines = []
for i, line in enumerate(lines):
    if "function pollPositions()" in line:
        poll_lines.append(i)
    if "window.renderOpenPositions = function" in line:
        render_lines.append(i)

print(f"Found {len(poll_lines)} pollPositions at lines: {poll_lines}")
print(f"Found {len(render_lines)} renderOpenPositions at lines: {render_lines}")

# Remove the FIRST pollPositions (orphan) and its entire block
# Find where it ends - look for the function definition after it
if len(poll_lines) >= 2:
    start = poll_lines[0]
    end = poll_lines[1]  # start of the second function
    # Get the "function pollPositions()" definition - go back to the comment/variable above it
    block_start = start
    for j in range(start - 3, start):
        if j >= 0 and ("/" in lines[j] or "var " in lines[j] or "function " in lines[j]):
            block_start = j
            break
    print(f"Removing lines {block_start} to {end - 1}")
    lines = lines[:block_start] + lines[end:]

# Now find the updated render lines
render_lines2 = []
for i, line in enumerate(lines):
    if "window.renderOpenPositions = function" in line:
        render_lines2.append(i)

print(f"After removal: {len(render_lines2)} renderOpenPositions at: {render_lines2}")

# Remove ALL but the LAST renderOpenPositions
if len(render_lines2) >= 2:
    for idx in reversed(render_lines2[:-1]):
        # Find end of this function - look for }, // or function at same indent
        end = idx + 1
        depth = 0
        in_func = False
        for j in range(idx, min(idx + 60, len(lines))):
            stripped = lines[j].strip()
            if "window.renderOpenPositions = function" in stripped:
                in_func = True
                continue
            if in_func:
                if "{" in stripped:
                    depth += stripped.count("{")
                if "}" in stripped:
                    depth -= stripped.count("}")
                    if depth <= 0 and "}" in stripped:
                        end = j + 1
                        break
        print(f"Removing renderOpenPositions from line {idx} to {end}")
        lines = lines[:idx] + lines[end:]

# Write back
with open("enhancer.js", "w") as f:
    f.writelines(lines)

# Verify
poll_cnt = sum(1 for l in lines if "function pollPositions()" in l)
render_cnt = sum(1 for l in lines if "window.renderOpenPositions = function" in l)
print(f"\nFinal counts: pollPositions={poll_cnt}, renderOpenPositions={render_cnt}")
