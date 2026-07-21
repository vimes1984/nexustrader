#!/usr/bin/env python3
"""Add /api/positions endpoint + render open positions in trades table."""
import os
os.chdir("/root/nexustrader")

# ========== 1. Add /api/positions endpoint to main.py ==========
with open("main.py") as f:
    c = f.read()

pos_endpoint = '''
@app.get("/api/positions")
async def api_positions():
    """Return currently open positions (in-memory, not from DB)."""
    import datetime as _dt
    orb = globals().get("orchestrator")
    if not orb:
        return {"positions": [], "count": 0}
    ee = orb.execution_engine
    positions = []
    for ticker, pos in ee.active_positions.items():
        entry_time_ts = pos.get("entry_time", 0)
        if isinstance(entry_time_ts, (int, float)) and entry_time_ts > 0:
            age_seconds = time.time() - entry_time_ts
        else:
            age_seconds = 0
        ticker_data = orb.data_ingestions.get(ticker)
        current_price = 0.0
        if ticker_data and ticker_data.data and len(ticker_data.data) > 0:
            current_price = float(ticker_data.data[-1].get("close", 0.0))
        entry_price = float(pos.get("entry_price", 0.0))
        quantity = float(pos.get("quantity", 0.0))
        if quantity > 0 and entry_price > 0 and current_price > 0:
            if pos.get("direction") == "BUY":
                unrealized_pnl = (current_price - entry_price) * quantity
            else:
                unrealized_pnl = (entry_price - current_price) * quantity
            unrealized_pnl_pct = (unrealized_pnl / (entry_price * quantity)) * 100 if entry_price * quantity > 0 else 0.0
        else:
            unrealized_pnl = 0.0
            unrealized_pnl_pct = 0.0
        positions.append({
            "symbol": ticker,
            "direction": pos.get("direction", "UNKNOWN"),
            "entry_price": round(entry_price, 6),
            "current_price": round(current_price, 6),
            "quantity": round(quantity, 6),
            "take_profit": round(float(pos.get("take_profit", 0.0)), 6),
            "stop_loss": round(float(pos.get("stop_loss", 0.0)), 6),
            "entry_time": entry_time_ts,
            "age_seconds": int(age_seconds),
            "unrealized_pnl": round(unrealized_pnl, 4),
            "unrealized_pnl_pct": round(unrealized_pnl_pct, 4),
            "fee_paid": round(float(pos.get("fee_paid", 0.0)), 4),
            "is_open": True
        })
    return {"positions": positions, "count": len(positions)}
'''

idx = c.rfind('if __name__ == "__main__":')
if idx >= 0:
    c = c[:idx] + pos_endpoint + "\n\n" + c[idx:]
    print("Added /api/positions endpoint")
else:
    print("ERROR: __main__ not found")

try:
    compile(c, "main.py", "exec")
    print("Syntax OK")
    with open("main.py", "w") as f:
        f.write(c)
except SyntaxError as e:
    print(f"ERROR: {e}")

# ========== 2. Update enhancer.js ==========
with open("dashboard/enhancer.js") as f:
    ej = f.read()

# Add renderOpenPositions to window and position polling
pos_code = '''
    // ============= RENDER OPEN POSITIONS IN TRADES TABLE =============
    window.renderOpenPositions = function(positions) {
        var tbody = document.getElementById('recent-trades-list');
        if (!tbody) return;
        
        // Remove any existing open-position rows
        var existing = tbody.querySelectorAll('.open-position-row');
        for (var i = 0; i < existing.length; i++) {
            existing[i].remove();
        }
        
        if (!positions || positions.length === 0) return;
        
        // Insert open positions at the top of the table
        for (var p = 0; p < positions.length; p++) {
            var pos = positions[p];
            var row = document.createElement("tr");
            row.className = "open-position-row";
            row.style.cssText = "background: rgba(16, 185, 129, 0.08); border-left: 3px solid var(--neon-green);";
            
            var entryD = new Date(pos.entry_time * 1000);
            var dateStr = entryD.toLocaleDateString([], { month: "short", day: "numeric" });
            var timeStr = entryD.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
            var sideColor = pos.direction === "BUY" ? "var(--neon-green)" : "var(--neon-red)";
            var pnlColor = pos.unrealized_pnl >= 0 ? "var(--neon-green)" : "var(--neon-red)";
            var pnlSign = pos.unrealized_pnl >= 0 ? "+" : "";
            
            var ageStr = "";
            if (pos.age_seconds > 3600) {
                ageStr = Math.round(pos.age_seconds / 3600) + "h";
            } else if (pos.age_seconds > 60) {
                ageStr = Math.round(pos.age_seconds / 60) + "m";
            } else {
                ageStr = pos.age_seconds + "s";
            }
            
            row.innerHTML = [
                '<td style="font-weight:600;">', dateStr, '</td>',
                '<td style="font-weight:600;">', timeStr, '</td>',
                '<td style="font-weight:600;">', pos.symbol, '</td>',
                '<td style="color:', sideColor, '; font-weight:600;">', pos.direction, ' <span style="font-size:10px;color:var(--text-muted);">', ageStr, '</span></td>',
                '<td>', pos.quantity.toFixed(4), '</td>',
                '<td>$', pos.entry_price.toFixed(4), '</td>',
                '<td style="color:var(--neon-blue);font-weight:600;">$', pos.current_price.toFixed(4), '</td>',
                '<td class="', pnlColor === "var(--neon-green)" ? "color-green" : "color-red", '" style="font-weight:600;">', pnlSign, '$', pos.unrealized_pnl.toFixed(2), ' (', pos.unrealized_pnl_pct.toFixed(1), '%)</td>',
                '<td><span style="background: rgba(16, 185, 129, 0.2); color: var(--neon-green); padding: 4px 8px; border-radius: 4px; font-size:11px; font-weight:600;">OPEN</span></td>',
            ].join("");
            
            // Insert at top of tbody
            if (tbody.firstChild) {
                tbody.insertBefore(row, tbody.firstChild);
            } else {
                tbody.appendChild(row);
            }
        }
    };
    
    // ============= POSITION POLLING =============
    function pollPositions() {
        fetch('/api/positions')
            .then(function(r) { return r.json(); })
            .then(function(data) {
                if (!data) return;
                var positions = data.positions || [];
                
                // Update active tactical position card
                var container = document.getElementById('position-details-container');
                if (container) {
                    if (!positions || positions.length === 0) {
                        container.innerHTML = '<p style="font-size: 13px; color: var(--text-muted); text-align: center; padding: 20px;">No Active Position Open</p>';
                    } else {
                        var pos = positions[0];
                        var sideClass = pos.direction === "BUY" ? "color-green" : "color-red";
                        var pnlClass = pos.unrealized_pnl >= 0 ? "color-green" : "color-red";
                        var pnlIcon = pos.unrealized_pnl >= 0 ? "&#9650;" : "&#9660;";
                        var html = '<div style="display: grid; grid-template-columns: 1fr 1fr; gap: 12px;">';
                        html += '<div><span style="font-size: 11px; color: var(--text-muted);">Symbol</span><br><strong>' + pos.symbol + '</strong></div>';
                        html += '<div><span style="font-size: 11px; color: var(--text-muted);">Direction</span><br><strong class="' + sideClass + '">' + pos.direction + '</strong></div>';
                        html += '<div><span style="font-size: 11px; color: var(--text-muted);">Entry</span><br><strong>$' + pos.entry_price.toFixed(4) + '</strong></div>';
                        html += '<div><span style="font-size: 11px; color: var(--text-muted);">Current</span><br><strong>$' + pos.current_price.toFixed(4) + '</strong></div>';
                        html += '<div><span style="font-size: 11px; color: var(--text-muted);">Qty</span><br><strong>' + pos.quantity.toFixed(4) + '</strong></div>';
                        html += '<div><span style="font-size: 11px; color: var(--text-muted);">Unrealized PnL</span><br><strong class="' + pnlClass + '">' + pnlIcon + ' $' + pos.unrealized_pnl.toFixed(2) + ' (' + pos.unrealized_pnl_pct.toFixed(2) + '%)</strong></div>';
                        html += '<div><span style="font-size: 11px; color: var(--text-muted);">TP</span><br><strong>$' + pos.take_profit.toFixed(4) + '</strong></div>';
                        html += '<div><span style="font-size: 11px; color: var(--text-muted);">SL</span><br><strong>$' + pos.stop_loss.toFixed(4) + '</strong></div>';
                        html += '</div>';
                        container.innerHTML = html;
                    }
                }
                
                // Also render at top of trades table
                if (typeof window.renderOpenPositions === "function") {
                    window.renderOpenPositions(positions);
                }
            })
            .catch(function(err) {
                console.error("[ENHANCER] pollPositions:", err);
            });
    }
    
'''

# Insert position code + init lastPositions var + add poll interval
# Strategy: find the last "var " block before boot, insert the window function and pollPositions there

old_section = "    var lastTradeCount = 0;"
new_section = "    var lastTradeCount = 0;\n    var lastPositions = [];"

if old_section in ej:
    ej = ej.replace(old_section, new_section)
    print("Added lastPositions var")
else:
    # Try different pattern
    for line in ["var lastTradeCount = 0;", "var lastTradeCount=0;"]:
        if line in ej:
            ej = ej.replace(line, line + "\n    var lastPositions = [];")
            print(f"Added lastPositions after {line.strip()}")
            break

# Insert position code + pollPositions function before boot()
boot_marker = "    function boot()"
idx = ej.find(boot_marker)
if idx >= 0:
    if pos_code not in ej:
        ej = ej[:idx] + pos_code + "\n    " + ej[idx:]
        print("Inserted position code before boot()")
else:
    print("WARN: boot() marker not found, trying backup")
    # Fall back to inserting before setInterval
    idx = ej.find("setInterval(pollTrades, 10000);")
    if idx >= 0:
        ej = ej[:idx + len("setInterval(pollTrades, 10000);")] + "\n        setInterval(pollPositions, 5000);" + ej[idx + len("setInterval(pollTrades, 10000);"):]
        print("Added pollPositions interval")
    else:
        print("WARN: pollTrades interval not found either")

# Add pollPositions interval if not already there
if "pollPositions" not in ej:
    # Find the poll interval section and add
    for marker in ["setInterval(pollTrades, 10000);", "setInterval(pollSignals, 5000);"]:
        if marker in ej:
            ej = ej.replace(marker, marker + "\n        setInterval(pollPositions, 5000);")
            print(f"Added pollPositions interval after {marker[:30]}...")
            break

with open("dashboard/enhancer.js", "w") as f:
    f.write(ej)
print("Saved enhancer.js")

# Bump version
print("\n=== Bumping version ===")
with open("dashboard/index.html") as f:
    html = f.read()
html = html.replace("enhancer.js?v=2.0", "enhancer.js?v=2.1")
with open("dashboard/index.html", "w") as f:
    f.write(html)
print("Bumped enhancer.js version to v=2.1")

print("\n=== DONE ===")
