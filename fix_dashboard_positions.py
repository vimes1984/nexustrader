#!/usr/bin/env python3
"""Patch dashboard.js to handle multi-position format from API."""

path = "/root/.openclaw/workspace/nexustrader/dashboard-v2/js/dashboard.js"
with open(path) as f:
    content = f.read()

# Replace renderPosition with renderPositions
old_func = '''  renderPosition(pos) {
    const c = byId('position-details-container'); if (!c) return;
    if (!pos?.entry_price) { c.innerHTML = '<span style="color:var(--text-muted)">No active position</span>'; return; }
    const dir = pos.direction || 'long';
    const dirColor = dir === 'long' ? 'var(--neon-green)' : 'var(--neon-red)';
    const pnl = Number(pos.unrealized_pnl || 0);
    c.innerHTML = `<div style="display:flex;justify-content:space-between;flex-wrap:wrap;gap:8px">
      <span style="color:${dirColor};font-weight:700;font-size:13px">${dir.toUpperCase()}</span>
      <span style="font-family:var(--font-mono)">Entry: <b>$${Number(pos.entry_price).toFixed(2)}</b></span>
      <span style="font-family:var(--font-mono)">Size: <b>${Number(pos.size||0).toFixed(4)}</b></span>
      <span style="font-family:var(--font-mono)">PnL: <b style="color:${pnl>=0?'var(--neon-green)':'var(--neon-red)'}">$${pnl.toFixed(4)}</b></span>
    </div>`;
  },'''

new_func = '''  renderPositions(positions) {
    const c = byId('position-details-container'); if (!c) return;
    if (!Array.isArray(positions) && typeof positions === 'object' && positions.entry_price) {
      return this.renderPositions([positions]);
    }
    let pa = positions;
    if (!Array.isArray(positions) && typeof positions === 'object') {
      pa = Object.entries(positions).map(function(e) { var p = e[1]; p.symbol = p.symbol || e[0]; return p; });
    }
    if (!pa || pa.length === 0) { c.innerHTML = '<span style="color:var(--text-muted)">No active positions</span>'; return; }
    c.innerHTML = pa.map(function(pos) {
      var dir = pos.direction || 'long';
      var dc = dir === 'long' ? 'var(--neon-green)' : 'var(--neon-red)';
      var pnl = Number(pos.unrealized_pnl || 0);
      var sym = pos.symbol || '\\u2014';
      return '<div style="display:flex;justify-content:space-between;flex-wrap:wrap;gap:8px;margin-bottom:4px;padding-bottom:4px;border-bottom:1px solid var(--border-subtle)">' +
        '<span style="color:var(--text-muted);font-weight:600;font-size:11px;min-width:55px">' + sym + '</span>' +
        '<span style="color:' + dc + ';font-weight:700;font-size:12px">' + dir.toUpperCase() + '</span>' +
        '<span style="font-family:var(--font-mono);font-size:11px">Entry: <b>$' + Number(pos.entry_price||0).toFixed(2) + '</b></span>' +
        '<span style="font-family:var(--font-mono);font-size:11px">Size: <b>' + Number(pos.size||pos.quantity||0).toFixed(4) + '</b></span>' +
        '<span style="font-family:var(--font-mono);font-size:11px">PnL: <b style="color:' + (pnl>=0?'var(--neon-green)':'var(--neon-red)') + '">$' + pnl.toFixed(4) + '</b></span>' +
      '</div>';
    }).join('');
  },'''

if old_func in content:
    content = content.replace(old_func, new_func)
    print("Replaced renderPosition -> renderPositions")
else:
    print("MISS: old_func not found")
    idx = content.find("renderPosition(pos)")
    if idx >= 0:
        print("Found at offset", idx, ":", repr(content[idx:idx+50]))

# Also fix the call site: data.position -> data.positions
old_call = '      if (data.positions) this.renderPositions(data.positions);\n      else if (data.position) this.renderPositions(data.position);'
# Already did this one above in previous edit — check current state
idx2 = content.find('data.position')
if idx2 >= 0:
    print("data.position still exists at offset", idx2, ":", repr(content[idx2:idx2+80]))

with open(path, "w") as f:
    f.write(content)
print("Done")
