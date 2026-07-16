import sqlite3
import json
import os
import logging

def get_data_dir():
    home = os.path.expanduser("~")
    data_dir = os.path.join(home, ".nexustrader")
    os.makedirs(data_dir, exist_ok=True)
    return data_dir

DB_FILE = os.path.join(get_data_dir(), "nexustrader.db")

def get_db_connection():
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    logging.info("Initializing SQLite database...")
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # Check if ticks table needs migration
    try:
        cursor.execute("PRAGMA table_info(ticks)")
        columns = [row[1] for row in cursor.fetchall()]
        if len(columns) > 0 and "symbol" not in columns:
            logging.info("Migrating ticks table: dropping old single-ticker ticks table...")
            cursor.execute("DROP TABLE ticks")
    except Exception as e:
        logging.error(f"Error checking ticks table schema: {e}")
    
    # Create ticks table (historical & live collected ticks with compound primary key)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS ticks (
        timestamp TEXT,
        symbol TEXT,
        open REAL,
        high REAL,
        low REAL,
        close REAL,
        volume REAL,
        rsi REAL,
        macd REAL,
        macd_signal REAL,
        bb_upper REAL,
        bb_lower REAL,
        atr REAL,
        PRIMARY KEY (timestamp, symbol)
    )
    """)
    
    # Create trades table (completed trades)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS trades (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        symbol TEXT,
        direction TEXT,
        quantity REAL,
        entry_price REAL,
        exit_price REAL,
        pnl REAL,
        pnl_percent REAL,
        exit_reason TEXT,
        entry_time REAL,
        exit_time REAL,
        strategy_signals TEXT
    )
    """)
    
    # Check if strategy_signals column exists, if not alter the table
    try:
        cursor.execute("PRAGMA table_info(trades)")
        columns = [row[1] for row in cursor.fetchall()]
        if "strategy_signals" not in columns:
            logging.info("Migrating trades table: adding strategy_signals column...")
            cursor.execute("ALTER TABLE trades ADD COLUMN strategy_signals TEXT")
    except Exception as e:
        logging.error(f"Error migrating trades table: {e}")
        
    # Create settings table (balance, weights)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS settings (
        key TEXT PRIMARY KEY,
        value TEXT
    )
    """)
    
    # Commit and close
    conn.commit()
    conn.close()
    logging.info("Database initialized successfully.")

def save_tick(row, symbol):
    """Saves a price tick to database."""
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("""
        INSERT OR REPLACE INTO ticks 
        (timestamp, symbol, open, high, low, close, volume, rsi, macd, macd_signal, bb_upper, bb_lower, atr)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            str(row['timestamp']),
            symbol,
            float(row.get('open', 0)),
            float(row.get('high', 0)),
            float(row.get('low', 0)),
            float(row.get('close', 0)),
            float(row.get('volume', 0)),
            float(row.get('rsi', 50)),
            float(row.get('macd', 0)),
            float(row.get('macd_signal', 0)),
            float(row.get('bb_upper', 0)),
            float(row.get('bb_lower', 0)),
            float(row.get('atr', 0))
        ))
        conn.commit()
    except Exception as e:
        logging.error(f"Error saving tick to db: {e}")
    finally:
        conn.close()

def save_trade(trade):
    """Saves a closed trade to database."""
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        signals_str = json.dumps(trade.get('strategy_signals', []))
        cursor.execute("""
        INSERT INTO trades (symbol, direction, quantity, entry_price, exit_price, pnl, pnl_percent, exit_reason, entry_time, exit_time, strategy_signals)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            trade['symbol'],
            trade['direction'],
            float(trade['quantity']),
            float(trade['entry_price']),
            float(trade['exit_price']),
            float(trade['pnl']),
            float(trade['pnl_percent']),
            trade['exit_reason'],
            float(trade['entry_time']),
            float(trade['exit_time']),
            signals_str
        ))
        conn.commit()
    except Exception as e:
        logging.error(f"Error saving trade to db: {e}")
    finally:
        conn.close()

def load_trades():
    """Loads all trades from database."""
    conn = get_db_connection()
    cursor = conn.cursor()
    trades = []
    try:
        cursor.execute("SELECT * FROM trades ORDER BY exit_time ASC")
        rows = cursor.fetchall()
        for r in rows:
            trade = dict(r)
            if "strategy_signals" in trade and trade["strategy_signals"]:
                try:
                    trade["strategy_signals"] = json.loads(trade["strategy_signals"])
                except Exception:
                    trade["strategy_signals"] = []
            else:
                trade["strategy_signals"] = []
            trades.append(trade)
    except Exception as e:
        logging.error(f"Error loading trades from db: {e}")
    finally:
        conn.close()
    return trades

def save_setting(key, value):
    """Saves system setting (json string or float/int)."""
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)", (key, str(value)))
        conn.commit()
    except Exception as e:
        logging.error(f"Error saving setting {key}: {e}")
    finally:
        conn.close()

def load_setting(key, default=None):
    """Loads system setting."""
    conn = get_db_connection()
    cursor = conn.cursor()
    val = default
    try:
        cursor.execute("SELECT value FROM settings WHERE key = ?", (key,))
        row = cursor.fetchone()
        if row:
            val = row[0]
    except Exception as e:
        logging.error(f"Error loading setting {key}: {e}")
    finally:
        conn.close()
    return val
