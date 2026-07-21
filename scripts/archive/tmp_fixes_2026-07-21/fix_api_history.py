# Fix /api/history to return proper OHLCV data plus accept tf/limit params
import re

with open("/root/nexustrader/main.py", "r") as f:
    main = f.read()

old = """@app.get("/api/history")
def get_ticker_history(ticker: str = "ETH-USD"):
    if ticker not in orchestrator.data_ingestions:
        return []
    
    ingest = orchestrator.data_ingestions[ticker]
    df = ingest.data.tail(40)
    history = []
    for idx, r in df.iterrows():
        # Handle index timestamp or column timestamp
        ts = str(idx)
        if 'timestamp' in r:
            ts = str(r['timestamp'])
        
        history.append({
            "timestamp": ts,
            "close": float(r['close']),
            "bb_upper": float(r.get('bb_upper', r['close'])),
            "bb_lower": float(r.get('bb_lower', r['close'])),
            "rsi": float(r.get('rsi', 50))
        })
    return history"""

new = """@app.get("/api/history")
def get_ticker_history(ticker: str = "ETH-USD", tf: int = 240, limit: int = 200):
    if ticker not in orchestrator.data_ingestions:
        return []
    
    ingest = orchestrator.data_ingestions[ticker]
    df = ingest.data.tail(min(limit, len(ingest.data)))
    history = []
    for idx, r in df.iterrows():
        # Handle timestamp from index or column
        if isinstance(idx, pd.Timestamp):
            ts = int(idx.timestamp())
        elif 'timestamp' in r:
            try:
                ts = int(pd.Timestamp(r['timestamp']).timestamp())
            except Exception:
                ts = int(time.mktime(time.strptime(str(r['timestamp'])[:19], '%Y-%m-%d %H:%M:%S'))) if str(r['timestamp'])[:10].isdigit() else int(float(r['timestamp']))
        else:
            ts = int(float(str(idx))) if str(idx).replace('.','',1).isdigit() else 0
        
        open_p = float(r.get('open', r.get('Open', r['close'])))
        high_p = float(r.get('high', r.get('High', r['close'])))
        low_p = float(r.get('low', r.get('Low', r['close'])))
        close_p = float(r['close'])
        volume_p = float(r.get('volume', r.get('Volume', 0)))
        
        history.append({
            "time": ts,
            "timestamp": str(r.get('timestamp', idx)),
            "open": open_p,
            "high": high_p,
            "low": low_p,
            "close": close_p,
            "volume": volume_p,
        })
    return history"""

if old in main:
    main = main.replace(old, new)
    print("Fix: /api/history now returns proper OHLCV with tf/limit params")
else:
    print("WARN: /api/history pattern not found - checking alternatives")
    # Check what the endpoint looks like
    import re
    m = re.search(r'@app\.get\("/api/history"\)', main)
    if m:
        start = m.start()
        # Find the function body
        print(f"Found at position {start}")
        # Print ~40 lines around it
        lines = main[start:start+1500].split('\n')
        for i, l in enumerate(lines[:30]):
            print(f"  {l[:120]}")
    else:
        print("Cannot find /api/history endpoint")

with open("/root/nexustrader/main.py", "w") as f:
    f.write(main)
