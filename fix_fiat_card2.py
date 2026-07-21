#!/usr/bin/env python3
"""Fix position card to show fiat holdings when no active positions."""
import os
os.chdir("/root/nexustrader/dashboard")

with open("enhancer.js") as f:
    c = f.read()

# Find the exact empty position block
old_block = """                    if (!positions || positions.length === 0) {
                        container.innerHTML = '<p style="font-size: 13px; color: var(--text-muted); text-align: center; padding: 20px;">No Active Position Open</p>';
                    } else {"""

new_block = """                    if (!positions || positions.length === 0) {
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
                    } else {"""

if old_block in c:
    c = c.replace(old_block, new_block)
    print("Updated position card empty state to show fiat holdings")
else:
    print("Pattern not found. Searching for exact match...")
    idx = c.find("No Active Position Open")
    if idx >= 0:
        # Show context around the match
        print(f"Found at {idx}")
        start = c.rfind("if (!positions", 0, idx)
        if start >= 0:
            end = c.find("} else {", idx)
            if end >= 0:
                print(f"Block from {start} to {end}:")
                print(c[start:end+8])
                print("---")
                print(repr(c[start:end+8]))

with open("enhancer.js", "w") as f:
    f.write(c)
print("Saved enhancer.js")
