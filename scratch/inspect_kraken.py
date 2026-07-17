import os
import json
import ccxt

def main():
    config_path = os.path.expanduser("~/.nexustrader/config.json")
    if not os.path.exists(config_path):
        print("Config file not found at", config_path)
        return
        
    with open(config_path, "r") as f:
        cfg = json.load(f)
        
    creds = cfg.get("api_credentials", {})
    api_key = creds.get("api_key")
    api_secret = creds.get("api_secret")
    broker = cfg.get("broker", "kraken").lower()
    
    if not api_key or not api_secret:
        print("No API credentials configured.")
        return
        
    exchange_class = getattr(ccxt, broker)
    exchange = exchange_class({
        'apiKey': api_key,
        'secret': api_secret,
        'enableRateLimit': True,
    })
    
    print("=== BALANCES ===")
    balance = exchange.fetch_balance()
    total_bal = balance.get('total', {})
    prices = {}
    try:
        # Fetch prices for conversion
        tickers = exchange.fetch_tickers(['BTC/EUR', 'ETH/EUR', 'SOL/EUR', 'DOGE/EUR', 'XRP/EUR'])
        prices = {sym.split('/')[0]: float(tick['last']) for sym, tick in tickers.items() if tick.get('last') is not None}
    except Exception as e:
        pass
        
    for asset, qty in total_bal.items():
        qty = float(qty)
        if qty > 0.000001:
            free = float(balance.get(asset, {}).get('free', 0.0))
            used = float(balance.get(asset, {}).get('used', 0.0))
            val_eur = qty
            if asset != 'EUR':
                if asset in prices:
                    val_eur = qty * prices[asset]
                else:
                    val_eur = 0.0
            print(f"Asset: {asset} | Total: {qty:.6f} | Free: {free:.6f} | Used: {used:.6f} | Value (EUR): €{val_eur:.2f}")
            
    print("\n=== OPEN ORDERS ===")
    try:
        orders = exchange.fetch_open_orders()
        if not orders:
            print("No open orders found.")
        for o in orders:
            print(f"ID: {o['id']} | Symbol: {o['symbol']} | Side: {o['side']} | Type: {o['type']} | Price: {o['price']} | Qty: {o['amount']} | Filled: {o['filled']}")
    except Exception as e:
        print("Error fetching open orders:", e)
        
    print("\n=== OPEN POSITIONS ===")
    try:
        if hasattr(exchange, 'fetch_positions'):
            positions = exchange.fetch_positions()
        else:
            positions = []
        if not positions:
            print("No open positions found.")
        for p in positions:
            print(f"Symbol: {p.get('symbol')} | Side: {p.get('side')} | Size: {p.get('contracts')} | Entry: {p.get('entryPrice')} | Mark: {p.get('markPrice')} | PnL: {p.get('unrealizedPnl')}")
    except Exception as e:
        print("Error fetching open positions:", e)

if __name__ == "__main__":
    main()
