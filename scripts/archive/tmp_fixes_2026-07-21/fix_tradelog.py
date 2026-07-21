"""
Fix three issues:
1. Trade log: sort by date desc, add full date column
2. Health alert polling in notification bell
3. Chart overflow CSS
"""
import re

# 1. Fix renderTradeLog
js_path = "/root/nexustrader/dashboard/app_v2.js"
with open(js_path) as f:
    js = f.read()

# Replace renderTradeLog to sort by exit_time desc and include full date
old_render = '''function renderTradeLog(trades) {
    completedTrades = trades || [];
    if (!trades || trades.length === 0) {
        elTradeLogBody.innerHTML = `<tr><td colspan="9" style="text-align: center; color: var(--text-muted); padding: 40px;">No trades completed yet. Watching the market for opportunities...</td></tr>`;
        return;
    }
    
    elTradeLogBody.innerHTML = "";
    
    // Render in reverse chronological order (newest first)
    [...trades].reverse().forEach(t => {
        const timeStr = new Date(t.exit_time * 1000).toLocaleTimeString();
        const pnlColor = t.pnl >= 0 ? "color-green" : "color-red";
        const sign = t.pnl >= 0 ? "+" : "";
        const outcomeBadge = t.pnl >= 0 ? "PROFIT" : "LOSS";
        const outcomeColor = t.pnl >= 0 ? "rgba(16, 185, 129, 0.15)" : "rgba(244, 63, 94, 0.15)";
        
        // Sum the weights of strategies that had a matching signal at entry
        // (Visual reference to show which strategies contributed to trade success)
        
        const row = document.createElement("tr");
        row.style.cursor = "pointer";
        row.innerHTML = `
            <td>${timeStr}</td>
            <td>${t.symbol}</td>
            <td style="color: ${t.direction === 'BUY' ? 'var(--neon-green)' : 'var(--neon-red)'}; font-weight:600;">${t.direction}</td>
            <td>${t.quantity.toFixed(4)}</td>
            <td>$${t.entry_price.toFixed(2)}</td>
            <td>$${t.exit_price.toFixed(2)}</td>
            <td>72%</td> <!-- Estimated base -->
            <td class="${pnlColor}" style="font-weight:600;">${sign}$${t.pnl.toFixed(2)} (${(t.pnl_percent*100).toFixed(2)}%)</td>
            <td><span style="background: ${outcomeColor}; color: ${t.pnl >= 0 ? 'var(--neon-green)' : 'var(--neon-red)'}; padding: 4px 8px; border-radius: 4px; font-size:11px; font-weight:600;">${t.exit_reason.toUpperCase()}</span></td>
        `;
        row.addEventListener("click", () => {
            openTradeDetailsModal(t);
        });
        elTradeLogBody.appendChild(row);
    });
}'''

new_render = '''function renderTradeLog(trades) {
    completedTrades = trades || [];
    if (!trades || trades.length === 0) {
        elTradeLogBody.innerHTML = `<tr><td colspan="10" style="text-align: center; color: var(--text-muted); padding: 40px;">No trades completed yet. Watching the market for opportunities...</td></tr>`;
        return;
    }
    
    elTradeLogBody.innerHTML = "";
    
    // Sort by exit_time descending (newest first)
    [...trades].sort(function(a, b) { return b.exit_time - a.exit_time; }).forEach(function(t) {
        var dt = new Date(t.exit_time * 1000);
        var dateStr = dt.toLocaleDateString([], { month: "short", day: "numeric", year: "numeric" });
        var timeStr = dt.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
        var pnlColor = t.pnl >= 0 ? "color-green" : "color-red";
        var sign = t.pnl >= 0 ? "+" : "";
        var outcomeColor = t.pnl >= 0 ? "rgba(16, 185, 129, 0.15)" : "rgba(244, 63, 94, 0.15)";
        
        var row = document.createElement("tr");
        row.style.cursor = "pointer";
        row.innerHTML = [
            '<td>', dateStr, '</td>',
            '<td>', timeStr, '</td>',
            '<td>', t.symbol, '</td>',
            '<td style="color: ', t.direction === "BUY" ? "var(--neon-green)" : "var(--neon-red)", '; font-weight:600;">', t.direction, '</td>',
            '<td>', t.quantity.toFixed(4), '</td>',
            '<td>$', t.entry_price.toFixed(2), '</td>',
            '<td>$', t.exit_price.toFixed(2), '</td>',
            '<td class="', pnlColor, '" style="font-weight:600;">', sign, '$', t.pnl.toFixed(2), ' (', (t.pnl_percent*100).toFixed(2), '%)</td>',
            '<td><span style="background: ', outcomeColor, '; color: ', t.pnl >= 0 ? "var(--neon-green)" : "var(--neon-red)", '; padding: 4px 8px; border-radius: 4px; font-size:11px; font-weight:600;">', (t.exit_reason || "UNKNOWN").toUpperCase(), '</span></td>',
        ].join("");
        row.addEventListener("click", function() {
            openTradeDetailsModal(t);
        });
        elTradeLogBody.appendChild(row);
    });
}'''

if old_render in js:
    js = js.replace(old_render, new_render)
    print("OK - renderTradeLog replaced (date column added, sorted by exit_time desc)")
else:
    print("FAIL - renderTradeLog block not found")
    # Find approximate location
    idx = js.find("function renderTradeLog(trades)")
    if idx >= 0:
        print("Found at", idx)
        print(js[idx:idx+150])

with open(js_path, "w") as f:
    f.write(js)

# Also update the table header colspan if needed
html_path = "/root/nexustrader/dashboard/index.html"
with open(html_path) as f:
    html = f.read()

# Check if the table header has Date column
if '<th>Time</th>' in html:
    html = html.replace('<th>Time</th>', '<th>Date</th><th>Time</th>')
    print("OK - added Date column header")
else:
    # Check what the header looks like
    import re
    m = re.search(r'<th>.*?</th>', html)
    if m:
        print("Table header looks like:", m.group())

with open(html_path, "w") as f:
    f.write(html)

print("\nDone")
