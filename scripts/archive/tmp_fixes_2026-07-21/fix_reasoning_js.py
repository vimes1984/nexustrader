"""Replace the updateReasoning function with enhanced version + fix buttons"""
with open("/root/nexustrader/dashboard/index.html") as f:
    html = f.read()

old_func = '''    function updateReasoning() {
        fetch("/api/trading/reasoning", { cache: "no-store" })
            .then(function(r) { return r.json(); })
            .then(function(d) {
                var el = document.getElementById("reasoning-text");
                if (!el) return;
                if (!d.reasons || d.reasons.length === 0) {
                    el.textContent = "Bot is operating normally.";
                    return;
                }
                var html = "";
                for (var i = 0; i < d.reasons.length; i++) {
                    var r = d.reasons[i];
                    var icon = r.type === "success" ? "\u2705" : r.type === "warning" ? "\u26a0\ufe0f" : r.type === "critical" ? "\ud83d\udd34" : r.type === "error" ? "\u274c" : "\u2139\ufe0f";
                    var color = r.type === "success" ? "var(--neon-green)" : r.type === "warning" ? "var(--neon-orange)" : r.type === "critical" ? "var(--neon-red)" : r.type === "error" ? "var(--neon-red)" : "var(--text-secondary)";
                    html += '<div style="margin-bottom:6px;font-size:12px;line-height:1.4;"><span style="color:' + color + ';">' + icon + "</span> <span>" + r.message + "</span></div>";
                }
                el.innerHTML = html;
                
                // Show reasoning panel
                var panel = document.getElementById("reasoning-panel");
                if (panel) panel.style.display = "block";
            })
            .catch(function() {});
    }'''

new_func = '''    function updateReasoning() {
        fetch("/api/trading/reasoning", { cache: "no-store" })
            .then(function(r) { return r.json(); })
            .then(function(d) {
                var container = document.getElementById("reasoning-items");
                var badge = document.getElementById("reasoning-summary-badge");
                var lastUpd = document.getElementById("reasoning-last-update");
                if (!container) return;
                
                // Update summary badge
                if (badge) {
                    var status = d.status || "unknown";
                    var colors = {active:"var(--neon-green)", inactive:"var(--neon-orange)", idle:"var(--neon-orange)", halted:"var(--neon-red)", error:"var(--neon-red)"};
                    var labels = {active:"ACTIVE", inactive:"LOW ACTIVITY", idle:"IDLE", halted:"HALTED", error:"ERROR"};
                    badge.textContent = labels[status] || status.toUpperCase();
                    badge.style.background = (colors[status] || "var(--text-secondary)") + "22";
                    badge.style.color = colors[status] || "var(--text-secondary)";
                    badge.style.border = "1px solid " + (colors[status] || "var(--text-secondary)");
                }
                if (lastUpd) {
                    var now = new Date();
                    lastUpd.textContent = now.getHours().toString().padStart(2,"0") + ":" + now.getMinutes().toString().padStart(2,"0") + ":" + now.getSeconds().toString().padStart(2,"0");
                }
                
                var items = d.items || [];
                if (items.length === 0) {
                    container.innerHTML = "<div style=\"text-align:center;padding:12px;color:var(--text-secondary);font-size:12px;\">Bot is operating normally.</div>";
                    return;
                }
                
                var icons = {success:"\\u2705", info:"\\u2139\\ufe0f", warning:"\\u26a0\\ufe0f", critical:"\\ud83d\\udd34", error:"\\u274c"};
                
                var html = "";
                for (var i = 0; i < items.length; i++) {
                    var item = items[i];
                    var sev = item.severity || "info";
                    var icon = icons[sev] || "\\u2139\\ufe0f";
                    var fix = item.fix;
                    
                    html += "<div class=\\"reason-item severity-" + sev + "\\" id=\\"ri-" + item.id + "\\">";
                    html += "<span class=\\"ri-icon\\">" + icon + "</span>";
                    html += "<div class=\\"ri-content\\">";
                    html += "<div class=\\"ri-title\\">" + (item.title || "") + "</div>";
                    html += "<div class=\\"ri-detail\\">" + (item.detail || "") + "</div>";
                    html += "<div class=\\"ri-fix-result\\" id=\\"fixr-" + item.id + "\\"></div>";
                    html += "</div>";
                    if (fix) {
                        var destClass = fix.destructive ? " destructive" : "";
                        html += "<button class=\\"ri-fix-btn" + destClass + "\\" data-action=\\"" + fix.action + "\\" data-label=\\"" + (fix.label || "Fix") + "\\">" + (fix.label || "Fix") + "</button>";
                    }
                    html += "</div>";
                }
                container.innerHTML = html;
                
                // Attach fix button handlers
                container.querySelectorAll(".ri-fix-btn").forEach(function(btn) {
                    btn.addEventListener("click", function() {
                        var action = this.dataset.action;
                        var origText = this.textContent;
                        this.disabled = true;
                        this.textContent = "Running...";
                        
                        var resultEl = this.parentElement.querySelector(".ri-fix-result");
                        if (resultEl) resultEl.style.display = "none";
                        
                        // Check for destructive actions
                        if (this.classList.contains("destructive")) {
                            if (!confirm("This action may affect active trading. Continue?")) {
                                this.disabled = false;
                                this.textContent = origText;
                                return;
                            }
                        }
                        
                        fetch("/api/trading/fix", {
                            method: "POST",
                            headers: {"Content-Type": "application/json"},
                            body: JSON.stringify({action: action}),
                            cache: "no-store"
                        })
                        .then(function(r) { return r.json(); })
                        .then(function(result) {
                            if (resultEl) {
                                resultEl.textContent = result.message || "Done";
                                resultEl.className = "ri-fix-result " + (result.status === "ok" ? "success" : "error");
                                resultEl.style.display = "block";
                            }
                            this.textContent = result.status === "ok" ? "\\u2705 Fixed" : "\\u274c Failed";
                            // Re-poll after fix
                            setTimeout(updateReasoning, 2000);
                        }.bind(this))
                        .catch(function(err) {
                            if (resultEl) {
                                resultEl.textContent = "Error: " + err.message;
                                resultEl.className = "ri-fix-result error";
                                resultEl.style.display = "block";
                            }
                            this.textContent = origText;
                            this.disabled = false;
                        }.bind(this));
                    });
                });
            })
            .catch(function(err) { console.warn("[FAILSAFE] Reasoning error:", err); });
    }
    
    // Poll reasoning faster than KPIs (every 5 seconds)
    var _reasoningTimer = setInterval(updateReasoning, 5000);'''

if old_func in html:
    html = html.replace(old_func, new_func)
    with open("/root/nexustrader/dashboard/index.html", "w") as f:
        f.write(html)
    print("OK - Reasoning function replaced with enhanced version")
else:
    print("FAIL - old function not found")
    # Debug
    idx = html.find("function updateReasoning")
    print("Found at", idx)
    if idx >= 0:
        print(html[idx:idx+150])
