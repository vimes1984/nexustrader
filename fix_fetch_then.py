#!/usr/bin/env python3
"""Fix broken fetchChartData function in enhancer.js - clean rewrite of the .then block."""
import os
os.chdir("/root/nexustrader/dashboard")

with open("enhancer.js") as f:
    c = f.read()

# Find and replace the broken .then block
old_then = """            .then(function(data) {
                if (!data || !data.length) return;
                var candles = [], volumes = [];
                for (var i = 0; i < data.length; i++) {
                    var d = data[i];
                    var ts = d.time || d.timestamp || 0; if (typeof ts === "string") ts = Math.floor(new Date(ts).getTime() / 1000); candles.push({ time: ts, value: d.close || d.price || 0 });
                                })
            .catch(function(err) { console.error('[ENHANCER] chart fetch err:', err); });"""

new_then = """            .then(function(data) {
                if (!data || !data.length) return;
                var candles = [];
                for (var i = 0; i < data.length; i++) {
                    var d = data[i];
                    var ts = d.time || d.timestamp || 0;
                    if (typeof ts === "string") ts = Math.floor(new Date(ts).getTime() / 1000);
                    candles.push({ time: ts, value: d.close || d.price || 0 });
                }
                lineSeries.setData(candles);
                console.log('[ENHANCER] chart', candles.length, 'candles loaded');
            })
            .catch(function(err) { console.error('[ENHANCER] chart fetch err:', err); });"""

if old_then in c:
    c = c.replace(old_then, new_then)
    print("Fixed fetchChartData .then block")
else:
    print("Pattern not found, looking for alternative...")
    idx = c.find("if (!data || !data.length) return;")
    if idx >= 0:
        print(f"Found at {idx}:")
        print(c[idx:idx+300])

with open("enhancer.js", "w") as f:
    f.write(c)
print("Saved enhancer.js")
