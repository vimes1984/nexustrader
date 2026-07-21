with open("/root/nexustrader/main.py") as f:
    content = f.read()

# Replace weights assignment with dict-safe version
old = '            weights = getattr(ens, "weights", {})'
new = '''            raw_w = getattr(ens, "weights", {})
            if isinstance(raw_w, dict):
                weights = raw_w
            elif isinstance(raw_w, (list, tuple)):
                used = [getattr(s, "name", str(s)) for s in ens.strategies]
                weights = {used[i]: float(raw_w[i]) for i in range(min(len(used), len(raw_w)))}
            else:
                weights = {}'''

if old in content:
    content = content.replace(old, new)
    with open("/root/nexustrader/main.py", "w") as f:
        f.write(content)
    print("OK - weights dict fix applied")
else:
    print("FAIL - not found")
    idx = content.find('weights')
    print("first 'weights' at", idx)
    print(repr(content[idx-20:idx+50]))
