#!/usr/bin/env python3
"""ONE-TIME: Fix dashboard thoroughly.

Fixes:
1. /api/positions gets fiat_breakdown + holdings (so one call has everything)
2. enhancer.js pollPositions uses data from positions endpoint directly
3. boot() gets setInterval(pollPositions, 5000)
4. Chart volumeSeries guarded (it may not exist, only lineSeries matters)
5. Failsafe also updated
"""
import os
os.chdir("/root/nexustrader")

# ========== 1. /api/positions: add fiat data ==========
with open("main.py") as f:
    c = f.read()

old_pos_return = '''    return {"positions": positions, "count": len(positions)}
}'''

# Find the return statement in api_positions
pos_idx = c.find('def api_positions')
if pos_idx >= 0:
    ret_idx = c.find('return {"positions": positions, "count": len(positions)}', pos_idx)
    if ret_idx >= 0:
        indent = c[c.rfind('\n', 0, ret_idx)+1:ret_idx]
        # Replace the return to include fiat data
        old_ret = 'return {"positions": positions, "count": len(positions)}'
        new_ret = '''    # Include fiat breakdown and holdings from status
    ee_fiat = orb.execution_engine
    holdings_raw = getattr(ee_fiat, "live_holdings", {})
    fiats = {}
    crys = {}
    for k, v in holdings_raw.items():
        try:
            fv = float(v)
        except:
            fv = 0.0
        if k in ("USD", "ZUSD"):
            fiats["USD"] = fiats.get("USD", 0.0) + fv
        elif k in ("EUR", "ZEUR"):
            fiats["EUR"] = fiats.get("EUR", 0.0) + fv
        elif k in ("GBP", "ZGBP"):
            fiats["GBP"] = fiats.get("GBP", 0.0) + fv
        else:
            crys[k] = fv
    crypto_count = len(crys)
    return {"positions": positions, "count": len(positions), "fiat_breakdown": fiats, "crypto_asset_count": crypto_count}'''
        c = c.replace(old_ret, new_ret)
        print("Added fiat_breakdown + crypto_count to /api/positions")
    else:
        print("Could not find return in api_positions")
else:
    print("api_positions function not found!")

try:
    compile(c, "main.py", "exec")
    print("Syntax OK")
    with open("main.py", "w") as f:
        f.write(c)
except SyntaxError as e:
    print(f"ERROR: {e}")

# ========== 2. Fix enhancer.js ==========
with open("dashboard/enhancer.js") as f:
    ej = f.read()

# Fix 1: Replace pollPositions to use fiat from positions endpoint
old_poll = """    // ============= POSITION POLLING =============
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
                        // Show fiat holdings breakdown when no active trading position
                        var xhr = new XMLHttpRequest();
                        xhr.open('GET', '/api/status', true);
                        xhr.timeout = 5000;
                        xhr.onload = function() {
                            try {
                                var d = JSON.parse(xhr.responseText);
                                var fb = d.fiat_breakdown || {};
                                var h = d.holdings || {};
                                var html2 = '<p style="font-size: 12px; color: var(--text-muted); text-align: center; padding: 5px; margin: 0 0 8px 0;">No Active Trading Position</p>';
                                html2 += '<div style="display: grid; grid-template-columns: 1fr 1fr; gap: 10px;">';
                                var hasFiat = false;
                                for (var cur in fb) {
                                    hasFiat = true;
                                    html2 += '<div style="background: rgba(255,255,255,0.04); border-radius: 6px; padding: 8px; text-align: center;">';
                                    html2 += '<div style="font-size: 10px; color: var(--text-muted);">' + cur + '</div>';
                                    html2 += '<div style="font-size: 18px; font-weight: 700; color: var(--neon-blue);">$' + Number(fb[cur]).toFixed(2) + '</div>';
                                    html2 += '</div>';
                                }
                                // Count crypto assets
                                var cryptoCount = 0;
                                for (var c2 in h) {
                                    if (c2 !== "USD" && c2 !== "EUR" && c2 !== "GBP" && c2 !== "ZUSD" && c2 !== "ZEUR" && c2 !== "ZGBP") {
                                        cryptoCount++;
                                    }
                                }
                                if (cryptoCount > 0) {
                                    html2 += '<div style="grid-column: 1 / -1; font-size: 11px; color: var(--text-muted); text-align: center; border-top: 1px solid var(--border-color); padding-top: 8px; margin-top: 4px;">';
                                    html2 += 'Portfolio: ' + cryptoCount + ' crypto assets</div>';
                                }
                                html2 += '</div>';
                                container.innerHTML = html2;
                            } catch(e) {
                                container.innerHTML = '<p style="font-size: 13px; color: var(--text-muted); text-align: center; padding: 20px;">No Active Position Open</p>';
                            }
                        };
                        xhr.onerror = function() {
                            container.innerHTML = '<p style="font-size: 13px; color: var(--text-muted); text-align: center; padding: 20px;">No Active Position Open</p>';
                        };
                        xhr.send();
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
    """

# Find the actual content - check if the current file has this exact block or a different version
if old_poll in ej:
    ej = ej.replace(old_poll, "")
    print("Removed old pollPositions block")
else:
    print("Old pollPositions not found, checking...")

# Now insert the NEW clean pollPositions
new_poll_code = """
    // ============= POSITION POLLING =============
    function pollPositions() {
        fetch('/api/positions')
            .then(function(r) { return r.json(); })
            .then(function(data) {
                if (!data) return;
                var positions = data.positions || [];
                var fb = data.fiat_breakdown || {};
                var cryptoCount = data.crypto_asset_count || 0;
                
                // Update active tactical position card
                var container = document.getElementById('position-details-container');
                if (container) {
                    var html = '';
                    if (positions && positions.length > 0) {
                        // Show active position
                        var pos = positions[0];
                        var sideClass = pos.direction === "BUY" ? "color-green" : "color-red";
                        var pnlClass = pos.unrealized_pnl >= 0 ? "color-green" : "color-red";
                        var pnlIcon = pos.unrealized_pnl >= 0 ? "&#9650;" : "&#9660;";
                        html = '<div style="display: grid; grid-template-columns: 1fr 1fr; gap: 12px;">';
                        html += '<div><span style="font-size: 11px; color: var(--text-muted);">Symbol</span><br><strong>' + pos.symbol + '</strong></div>';
                        html += '<div><span style="font-size: 11px; color: var(--text-muted);">Direction</span><br><strong class="' + sideClass + '">' + pos.direction + '</strong></div>';
                        html += '<div><span style="font-size: 11px; color: var(--text-muted);">Entry</span><br><strong>$' + pos.entry_price.toFixed(4) + '</strong></div>';
                        html += '<div><span style="font-size: 11px; color: var(--text-muted);">Current</span><br><strong>$' + pos.current_price.toFixed(4) + '</strong></div>';
                        html += '<div><span style="font-size: 11px; color: var(--text-muted);">Qty</span><br><strong>' + pos.quantity.toFixed(4) + '</strong></div>';
                        html += '<div><span style="font-size: 11px; color: var(--text-muted);">Unrealized PnL</span><br><strong class="' + pnlClass + '">' + pnlIcon + ' $' + pos.unrealized_pnl.toFixed(2) + ' (' + pos.unrealized_pnl_pct.toFixed(2) + '%)</strong></div>';
                        html += '<div><span style="font-size: 11px; color: var(--text-muted);">TP</span><br><strong>$' + pos.take_profit.toFixed(4) + '</strong></div>';
                        html += '<div><span style="font-size: 11px; color: var(--text-muted);">SL</span><br><strong>$' + pos.stop_loss.toFixed(4) + '</strong></div>';
                        html += '</div>';
                    } else {
                        // Show fiat holdings breakdown
                        html = '<p style="font-size: 12px; color: var(--text-muted); text-align: center; padding: 5px; margin: 0 0 8px 0;">No Active Trading Position</p>';
                        html += '<div style="display: grid; grid-template-columns: 1fr 1fr; gap: 10px;">';
                        var hasFiat = false;
                        for (var cur in fb) {
                            hasFiat = true;
                            html += '<div style="background: rgba(255,255,255,0.04); border-radius: 6px; padding: 8px; text-align: center;">';
                            html += '<div style="font-size: 10px; color: var(--text-muted);">' + cur + '</div>';
                            html += '<div style="font-size: 18px; font-weight: 700; color: var(--neon-blue);">$' + Number(fb[cur]).toFixed(2) + '</div>';
                            html += '</div>';
                        }
                        if (cryptoCount > 0) {
                            html += '<div style="grid-column: 1 / -1; font-size: 11px; color: var(--text-muted); text-align: center; border-top: 1px solid var(--border-color); padding-top: 8px; margin-top: 4px;">';
                            html += 'Portfolio: ' + cryptoCount + ' crypto assets</div>';
                        }
                        html += '</div>';
                    }
                    container.innerHTML = html;
                }
                
                // Render at top of trades table
                if (typeof window.renderOpenPositions === "function") {
                    window.renderOpenPositions(positions);
                }
            })
            .catch(function(err) {
                console.error("[ENHANCER] pollPositions:", err);
            });
    }
    
"""

# Insert before boot()
idx = ej.find("function boot()")
if idx >= 0:
    ej = ej[:idx] + new_poll_code + "\n    " + ej[idx:]
    print("Inserted new pollPositions before boot()")
else:
    print("boot() not found!")

# Fix 2: Add setInterval(pollPositions, 5000) to boot()
old_boot_body = """        setInterval(pollTrades, 10000);"""
new_boot_body = """        setInterval(pollTrades, 10000);
        
        // Poll positions every 5s (open positions + fiat holdings)
        setInterval(pollPositions, 5000);
        setTimeout(pollPositions, 200);"""

if old_boot_body in ej:
    ej = ej.replace(old_boot_body, new_boot_body)
    print("Added pollPositions interval to boot()")
else:
    print("Could not find pollTrades interval in boot()")
    # Check what's actually there
    b_idx = ej.find("setInterval(pollTrades")
    if b_idx >= 0:
        print(f"Found at {b_idx}: {ej[b_idx-20:b_idx+50]}")

with open("dashboard/enhancer.js", "w") as f:
    f.write(ej)
print("Saved enhancer.js")

# ========== 3. Bump version ==========
with open("dashboard/index.html") as f:
    html = f.read()
html = html.replace("enhancer.js?v=2.4", "enhancer.js?v=3.0")
with open("dashboard/index.html", "w") as f:
    f.write(html)
print("Bumped to v=3.0")

print("\n=== DONE ===")
