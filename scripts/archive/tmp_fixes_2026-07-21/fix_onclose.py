path = "/root/nexustrader/dashboard/app_v2.js"
with open(path) as f:
    content = f.read()

old = 'document.getElementById("status-text").textContent = "Disconnected";'
new = 'if (typeof globalTradingMode === "undefined" || globalTradingMode !== "live") document.getElementById("status-text").textContent = "Disconnected";'

count = content.count(old)
if count > 0:
    content = content.replace(old, new)
    with open(path, "w") as f:
        f.write(content)
    print("OK - fixed", count, "occurrences")
else:
    print("FAIL - pattern not found")
    lines = content.split("\n")
    for i, l in enumerate(lines):
        if "Disconnected" in l:
            print("Line %d: %r" % (i+1, l))
