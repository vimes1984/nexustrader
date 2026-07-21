#!/usr/bin/env python3
"""Fix Real-Time Probability Estimation and Charts.

Fixes:
1. pollSignals: data.tickers[ticker] → data[ticker] (API returns flat ticker dict, not nested)
2. Chart: addLineSeries instead of addCandlestickSeries (history only has close price)
3. fetchChartData: map timestamp → time, use close for line chart
"""
import os
os.chdir("/root/nexustrader/dashboard")

# ========== Fix enhancer.js ==========
with open("enhancer.js") as f:
    ej = f.read()

# Fix 1: pollSignals - data.tickers → data directly
fixes = [
    ("if (!data || !data.tickers) return;",
     "if (!data) return;"),
    ("var keys = Object.keys(data.tickers);",
     "var keys = Object.keys(data);"),
    ("data.tickers[keys[i]]",
     "data[keys[i]]"),
    ("data.tickers[ticker]",
     "data[ticker]"),
    ("tickerData = data.tickers[ticker]",
     "tickerData = data[ticker]"),
]

for old, new in fixes:
    if old in ej:
        ej = ej.replace(old, new)
        print(f"Fixed: {old[:40]}...")
    else:
        # Try with single quotes
        old2 = old.replace('"', "'")
        new2 = new.replace('"', "'")
        if old2 in ej:
            ej = ej.replace(old2, new2)
            print(f"Fixed (sq): {old2[:40]}...")
        else:
            print(f"Not found: {old[:40]}...")

# Fix 2: Change chart from candlestick to line series
# Replace candlestick series with line series
if "addCandlestickSeries" in ej:
    ej = ej.replace(
        """            candlestickSeries = chartInstance.addCandlestickSeries({
                upColor: '#22c55e', downColor: '#ef4444',
                borderDownColor: '#ef4444', borderUpColor: '#22c55e',
                wickDownColor: '#ef4444', wickUpColor: '#22c55e',
            });""",
        """            lineSeries = chartInstance.addLineSeries({
                color: '#22c55e',
                lineWidth: 2,
                crosshairMarkerVisible: true,
                priceFormat: { type: 'price' },
            });"""
    )
    print("Changed addCandlestickSeries → addLineSeries")

# Fix 3: Replace addHistogramSeries with area series for volume
if "addHistogramSeries" in ej:
    ej = ej.replace(
        "chartInstance.addHistogramSeries({",
        "chartInstance.addAreaSeries({"
    )
    ej = ej.replace(
        """                volumeSeries = chartInstance.addHistogramSeries({
                priceFormat: { type: 'volume' },
                priceScaleId: 'volume',
            });
            chartInstance.priceScale('volume').applyOptions({ scaleMargins: { top: 0.85, bottom: 0 } });""",
        """                volumeSeries = chartInstance.addAreaSeries({
                lineColor: '#2563eb',
                topColor: 'rgba(37,99,235,0.3)',
                bottomColor: 'rgba(37,99,235,0.01)',
                priceFormat: { type: 'volume' },
                priceScaleId: 'volume',
            });
            chartInstance.priceScale('volume').applyOptions({ scaleMargins: { top: 0.8, bottom: 0 } });"""
    )
    print("Changed addHistogramSeries → addAreaSeries")

# Fix 4: fetchChartData - map timestamp to time, use close for line
old_fetch = """            candles.push({ time: d.time, open: d.open, high: d.high, low: d.low, close: d.close });
                    volumes.push({ time: d.time, value: d.volume || 0, color: d.close >= d.open ? "rgba(34,197,94,0.4)" : "rgba(239,68,68,0.4)" });"""
new_fetch = """                    var ts = d.time || d.timestamp || 0;
                    if (typeof ts === "string") ts = Math.floor(new Date(ts).getTime() / 1000);
                    candles.push({ time: ts, value: d.close || d.price || 0 });
                    volumes.push({ time: ts, value: (d.volume || d.vol || 0) / 10, color: "rgba(37,99,235,0.3)" });"""

if old_fetch in ej:
    ej = ej.replace(old_fetch, new_fetch)
    print("Fixed fetchChartData format")
else:
    print("fetchChartData pattern not found, checking...")
    if "d.time" in ej:
        # Different pattern - find it
        import re
        idx = ej.find("candles.push")
        if idx >= 0:
            print(f"Found candles.push at {idx}: {ej[idx:idx+100]}")

# Fix 5: Change setData call for line series
if "candlestickSeries.setData(candles)" in ej:
    ej = ej.replace("candlestickSeries.setData(candles)", "lineSeries.setData(candles)")
    print("Fixed setData → lineSeries")
else:
    # Maybe it's already lineSeries or different name
    if "lineSeries" in ej and "lineSeries.setData" not in ej:
        # Find what setData is called on
        idx = ej.find(".setData(")
        if idx >= 0:
            print(f"Found setData call: {ej[idx-30:idx+30]}")

# Fix 6: Also update the volume line update
try:
    with open("enhancer.js", "w") as f:
        f.write(ej)
    print("\nSaved enhancer.js")
except Exception as e:
    print(f"Error saving: {e}")

# ========== Fix failsafe chart in index.html ==========
with open("index.html") as f:
    html = f.read()

# Fix failsafe: same changes - candlestick → line
if "addCandlestickSeries" in html:
    html = html.replace(
        """        candlestickSeries = chartInstance.addCandlestickSeries({
            upColor:"#22c55e", downColor:"#ef4444",
            borderDownColor:"#ef4444", borderUpColor:"#22c55e",
            wickDownColor:"#ef4444", wickUpColor:"#22c55e",
        });
        
        chartInstance.addHistogramSeries({""",
        """        lineSeries = chartInstance.addLineSeries({
            color:"#22c55e",
            lineWidth: 2,
            crosshairMarkerVisible: true,
        });
        
        chartInstance.addAreaSeries({"""
    )
    print("Fixed failsafe candlestick → line")
    
    html = html.replace(
        """            priceFormat: { type: "volume" },
            priceScaleId: "volume",
        });
        chartInstance.priceScale("volume").applyOptions({ scaleMargins: { top: 0.85, bottom: 0 } });""",
        """            priceFormat: { type: "volume" },
            priceScaleId: "volume",
        });
        chartInstance.priceScale("volume").applyOptions({ scaleMargins: { top: 0.8, bottom: 0 } });"""
    )

# Fix failsafe fetchChartData
old_fs_fetch = """                    candles.push({ time: d.time, open: d.open, high: d.high, low: d.low, close: d.close });
                    volumes.push({ time: d.time, value: d.volume || 0, color: d.close >= d.open ? "rgba(34,197,94,0.4)" : "rgba(239,68,68,0.4)" });"""
new_fs_fetch = """                    var ts = d.time || d.timestamp || 0;
                    if (typeof ts === "string") ts = Math.floor(new Date(ts).getTime() / 1000);
                    candles.push({ time: ts, value: d.close || d.price || 0 });
                    volumes.push({ time: ts, value: (d.volume || d.vol || 0) / 10, color: "rgba(37,99,235,0.3)" });"""

if old_fs_fetch in html:
    html = html.replace(old_fs_fetch, new_fs_fetch)
    print("Fixed failsafe fetchChartData")
else:
    print("failsafe fetch pattern not found")

# Fix failsafe setData
if "candlestickSeries.setData(candles)" in html:
    html = html.replace("candlestickSeries.setData(candles)", "lineSeries.setData(candles)")
    print("Fixed failsafe setData")

try:
    with open("index.html", "w") as f:
        f.write(html)
    print("Saved index.html")
except Exception as e:
    print(f"Error saving: {e}")
