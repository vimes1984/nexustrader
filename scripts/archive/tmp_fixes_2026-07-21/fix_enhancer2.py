js_path = "/root/nexustrader/dashboard/enhancer.js"
with open(js_path) as f:
    js = f.read()

alert_code = """
    // ============= HEALTH ALERT POLLING =============
    function pollAlerts() {
        var xhr = new XMLHttpRequest();
        xhr.open("GET", "/api/alerts", true);
        xhr.timeout = 10000;
        xhr.onload = function() {
            if (xhr.status !== 200) return;
            try {
                var data = JSON.parse(xhr.responseText);
                var alerts = data.alerts || (Array.isArray(data) ? data : []);
                var count = 0;
                for (var i = 0; i < alerts.length; i++) {
                    if (!alerts[i].resolved && !alerts[i].acknowledged) count++;
                }
                var badge = document.getElementById("notification-badge");
                if (badge) {
                    if (count > 0) {
                        badge.textContent = count;
                        badge.style.display = "block";
                        badge.style.background = count > 0 ? "var(--neon-red)" : "var(--neon-orange)";
                    } else {
                        badge.style.display = "none";
                    }
                }
                var list = document.getElementById("notification-list");
                if (list && alerts.length > 0) {
                    var unacked = alerts.filter(function(a) { return !a.resolved && !a.acknowledged; });
                    if (unacked.length > 0) {
                        list.innerHTML = "";
                        unacked.forEach(function(a) {
                            var item = document.createElement("div");
                            item.style.cssText = "padding:8px 10px;border-radius:6px;background:rgba(255,255,255,0.04);border-left:3px solid var(--neon-red);margin-bottom:6px;";
                            var cat = a.category || "system";
                            var msg = a.message || a.alert_type || "Unknown alert";
                            var time = a.created_at ? new Date(a.created_at * 1000).toLocaleTimeString() : "";
                            item.innerHTML = "<div style=\"font-weight:600;font-size:11px;\">" + cat.toUpperCase() + "</div>" +
                                "<div style=\"font-size:12px;color:var(--text-primary);\">" + msg + "</div>" +
                                "<div style=\"font-size:10px;color:var(--text-muted);margin-top:2px;\">" + time + "</div>";
                            list.appendChild(item);
                        });
                    }
                }
            } catch(e) {
                console.warn("[ENHANCER] alert parse:", e);
            }
        };
        xhr.onerror = function() {};
        xhr.send();
    }
"""

# Insert before EVENTS section
old = "    // ============= EVENTS ============="
new = alert_code + "\n" + old
if old in js:
    js = js.replace(old, new)
    print("OK - alert polling added")
else:
    print("FAIL - EVENTS marker not found")

# Fix chart overflow
old_css = "wrap.style.cssText = 'height:350px;width:100%;position:relative;';"
new_css = "wrap.style.cssText = 'height:350px;width:100%;position:relative;overflow:hidden;';"
js = js.replace(old_css, new_css)
print("OK - chart overflow:hidden added")

# Add pollAlerts to boot
old_boot = "        // Poll KPI\n        setInterval(pollKpiPnL, 5000);"
new_boot = "        // Poll KPI and alerts\n        setInterval(pollKpiPnL, 5000);\n        setTimeout(pollAlerts, 2000);\n        setInterval(pollAlerts, 30000);"
if old_boot in js:
    js = js.replace(old_boot, new_boot)
    print("OK - boot updated with alert polling")
else:
    print("FAIL - boot marker not found")

with open(js_path, "w") as f:
    f.write(js)

print("\nDone")
