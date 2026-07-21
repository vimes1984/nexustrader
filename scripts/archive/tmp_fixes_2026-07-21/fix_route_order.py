#!/usr/bin/env python3
"""Fix route ordering: /apply/all must be defined BEFORE /apply/{opt_id}"""
B = "/root/nexustrader"
with open(f"{B}/main.py") as f:
    m = f.read()

# Find both route blocks
all_start = m.find('@app.post("/api/optimizations/apply/all")')
optid_start = m.find('@app.post("/api/optimizations/apply/{opt_id}")')

print(f"apply/all at: {all_start}")
print(f"apply/{{opt_id}} at: {optid_start}")

if all_start == -1 or optid_start == -1:
    print("ERROR: routes not found")
    exit(1)

if all_start < optid_start:
    print("Order already correct?!")
    exit(0)

# Extract the /apply/all block (ends at the next @app. decorator)
next_route = m.find('\n@app.', all_start + 10)
all_block = m[all_start:next_route]

# Remove it from current position
m = m[:all_start] + m[next_route+1:]

# Re-find optid position (shifted after removal)
optid_start = m.find('@app.post("/api/optimizations/apply/{opt_id}")')

# Insert /apply/all before /apply/{opt_id}
m = m[:optid_start] + all_block + '\n\n' + m[optid_start:]

compile(m, "main.py", "exec")
print("Compile OK")
with open(f"{B}/main.py", "w") as f:
    f.write(m)
print("Fixed: /apply/all now defined before /apply/{opt_id}")
