import sqlite3
import json
import os
import logging
import time

def get_data_dir():
    home = os.path.expanduser("~")
    data_dir = os.path.join(home, ".nexustrader")
    os.makedirs(data_dir, exist_ok=True)
    return data_dir

DB_FILE = os.path.join(get_data_dir(), "nexustrader.db")
DB_PATH = DB_FILE

def get_db_connection():
    conn = sqlite3.connect(DB_FILE, timeout=30.0)
    conn.row_factory = sqlite3.Row
    try:
        conn.execute("PRAGMA journal_mode=WAL")
    except Exception:
        pass
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
        strategy_signals TEXT,
        sentiment_sources TEXT
    )
    """)
    
    # Check if strategy_signals/sentiment_sources columns exist, if not alter the table
    try:
        cursor.execute("PRAGMA table_info(trades)")
        columns = [row[1] for row in cursor.fetchall()]
        if "strategy_signals" not in columns:
            logging.info("Migrating trades table: adding strategy_signals column...")
            cursor.execute("ALTER TABLE trades ADD COLUMN strategy_signals TEXT")
        if "sentiment_sources" not in columns:
            logging.info("Migrating trades table: adding sentiment_sources column...")
            cursor.execute("ALTER TABLE trades ADD COLUMN sentiment_sources TEXT")
        if "policy_brain" not in columns:
            logging.info("Migrating trades table: adding policy_brain column...")
            cursor.execute("ALTER TABLE trades ADD COLUMN policy_brain TEXT")
        if "trading_mode" not in columns:
            logging.info("Migrating trades table: adding trading_mode column...")
            cursor.execute("ALTER TABLE trades ADD COLUMN trading_mode TEXT DEFAULT 'paper'")
    except Exception as e:
        logging.error(f"Error migrating trades table: {e}")

    # Check and migrate policy_brains table
    try:
        cursor.execute("PRAGMA table_info(policy_brains)")
        pb_cols = [row[1] for row in cursor.fetchall()]
        if len(pb_cols) > 0:
            if "training_steps" not in pb_cols:
                logging.info("Migrating policy_brains table: adding training_steps column...")
                cursor.execute("ALTER TABLE policy_brains ADD COLUMN training_steps INTEGER DEFAULT 0")
            if "accumulated_trades" not in pb_cols:
                logging.info("Migrating policy_brains table: adding accumulated columns...")
                cursor.execute("ALTER TABLE policy_brains ADD COLUMN accumulated_trades INTEGER DEFAULT 0")
                cursor.execute("ALTER TABLE policy_brains ADD COLUMN accumulated_pnl REAL DEFAULT 0.0")
                cursor.execute("ALTER TABLE policy_brains ADD COLUMN accumulated_pnl_percent REAL DEFAULT 0.0")
                cursor.execute("ALTER TABLE policy_brains ADD COLUMN accumulated_wins INTEGER DEFAULT 0")
                
                # Backfill stats from trades table for existing brains
                try:
                    logging.info("Backfilling accumulated stats from trades table for existing brains...")
                    cursor.execute("SELECT DISTINCT policy_brain FROM trades WHERE policy_brain IS NOT NULL")
                    brains = [row[0] for row in cursor.fetchall()]
                    for brain_name in brains:
                        cursor.execute(
                            """
                            SELECT COUNT(*), SUM(pnl), SUM(pnl_percent), COUNT(case when pnl > 0 then 1 end) 
                            FROM trades 
                            WHERE policy_brain = ?
                            """,
                            (brain_name,)
                        )
                        cnt, total_pnl, total_pnl_percent, wins = cursor.fetchone()
                        cnt = cnt or 0
                        total_pnl = total_pnl or 0.0
                        total_pnl_percent = total_pnl_percent or 0.0
                        wins = wins or 0
                        
                        cursor.execute(
                            """
                            UPDATE policy_brains 
                            SET accumulated_trades = ?,
                                accumulated_pnl = ?,
                                accumulated_pnl_percent = ?,
                                accumulated_wins = ?
                            WHERE name = ?
                            """,
                            (cnt, total_pnl, total_pnl_percent, wins, brain_name)
                        )
                    logging.info("Backfilled stats successfully.")
                except Exception as ex:
                    logging.error(f"Error backfilling stats: {ex}")
    except Exception as e:
        logging.error(f"Error migrating policy_brains table: {e}")
        
    # Standalone check to backfill if the migration was already run but columns are still zero
    try:
        cursor.execute("SELECT SUM(accumulated_trades) FROM policy_brains")
        sum_acc = cursor.fetchone()[0] or 0
        if sum_acc == 0:
            cursor.execute("SELECT COUNT(*) FROM trades")
            trades_count = cursor.fetchone()[0] or 0
            if trades_count > 0:
                logging.info("Standalone check: Backfilling accumulated stats from trades table...")
                cursor.execute("SELECT DISTINCT policy_brain FROM trades WHERE policy_brain IS NOT NULL")
                brains = [row[0] for row in cursor.fetchall()]
                for brain_name in brains:
                    cursor.execute(
                        """
                        SELECT COUNT(*), SUM(pnl), SUM(pnl_percent), COUNT(case when pnl > 0 then 1 end) 
                        FROM trades 
                        WHERE policy_brain = ?
                        """,
                        (brain_name,)
                    )
                    cnt, total_pnl, total_pnl_percent, wins = cursor.fetchone()
                    cnt = cnt or 0
                    total_pnl = total_pnl or 0.0
                    total_pnl_percent = total_pnl_percent or 0.0
                    wins = wins or 0
                    
                    cursor.execute(
                        """
                        UPDATE policy_brains 
                        SET accumulated_trades = ?,
                            accumulated_pnl = ?,
                            accumulated_pnl_percent = ?,
                            accumulated_wins = ?
                        WHERE name = ?
                        """,
                        (cnt, total_pnl, total_pnl_percent, wins, brain_name)
                    )
                logging.info("Standalone backfill completed successfully.")
    except Exception as ex:
        logging.error(f"Error checking/running standalone backfill: {ex}")
        
    # Create settings table (balance, weights)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS settings (
        key TEXT PRIMARY KEY,
        value TEXT
    )
    """)
    
    # Create portfolio history table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS portfolio_history (
        timestamp REAL PRIMARY KEY,
        equity REAL,
        pnl REAL
    )
    """)

    # Create weights history table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS weights_history (
        timestamp REAL,
        ticker TEXT,
        weights TEXT,
        PRIMARY KEY (timestamp, ticker)
    )
    """)
    
    # Create policy brains table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS policy_brains (
        name TEXT,
        ticker TEXT,
        model_dna TEXT,
        weights TEXT,
        created_at REAL,
        training_steps INTEGER DEFAULT 0,
        accumulated_trades INTEGER DEFAULT 0,
        accumulated_pnl REAL DEFAULT 0.0,
        accumulated_pnl_percent REAL DEFAULT 0.0,
        accumulated_wins INTEGER DEFAULT 0,
        PRIMARY KEY (name, ticker)
    )
    """)
    
    # Commit and close
    conn.commit()
    conn.close()
    logging.info("Database initialized successfully.")

def save_weights_history(timestamp: float, ticker: str, weights: dict):
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute(
            "INSERT OR REPLACE INTO weights_history (timestamp, ticker, weights) VALUES (?, ?, ?)",
            (timestamp, ticker, json.dumps(weights))
        )
        conn.commit()
        conn.close()
    except Exception as e:
        logging.error(f"Error saving weights history: {e}")

def load_weights_history(ticker: str, limit: int = 100):
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute(
            "SELECT timestamp, weights FROM weights_history WHERE ticker = ? ORDER BY timestamp ASC LIMIT ?",
            (ticker, limit)
        )
        rows = cursor.fetchall()
        conn.close()
        return [{"timestamp": r[0], "weights": json.loads(r[1])} for r in rows]
    except Exception as e:
        logging.error(f"Error loading weights history: {e}")
        return []

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
        sources_str = json.dumps(trade.get('sentiment_sources', {}))
        cursor.execute("""
        INSERT INTO trades (symbol, direction, quantity, entry_price, exit_price, pnl, pnl_percent, exit_reason, entry_time, exit_time, strategy_signals, sentiment_sources, policy_brain, trading_mode)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
            signals_str,
            sources_str,
            trade.get('policy_brain', 'Default Brain'),
            trade.get('trading_mode', 'paper')
        ))
        
        # Update policy_brain's accumulated efficacy metrics
        brain_name = trade.get('policy_brain', 'Default Brain')
        pnl = float(trade['pnl'])
        pnl_percent = float(trade['pnl_percent'])
        is_win = 1 if pnl > 0 else 0
        cursor.execute(
            """
            UPDATE policy_brains 
            SET accumulated_trades = accumulated_trades + 1,
                accumulated_pnl = accumulated_pnl + ?,
                accumulated_pnl_percent = accumulated_pnl_percent + ?,
                accumulated_wins = accumulated_wins + ?
            WHERE name = ? AND ticker = ?
            """,
            (pnl, pnl_percent, is_win, brain_name, trade['symbol'])
        )
        conn.commit()
    except Exception as e:
        logging.error(f"Error saving trade to db: {e}")
    finally:
        conn.close()

def load_trades(trading_mode=None):
    """Loads trades from database, optionally filtered by trading_mode."""
    conn = get_db_connection()
    cursor = conn.cursor()
    trades = []
    try:
        if trading_mode:
            cursor.execute("SELECT * FROM trades WHERE trading_mode = ? ORDER BY exit_time ASC", (trading_mode,))
        else:
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
                
            if "sentiment_sources" in trade and trade["sentiment_sources"]:
                try:
                    trade["sentiment_sources"] = json.loads(trade["sentiment_sources"])
                except Exception:
                    trade["sentiment_sources"] = {}
            else:
                trade["sentiment_sources"] = {}
                
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

# -------------------------------------------------------------
# Neural Policy Brains Table Operations
# -------------------------------------------------------------
def save_policy_brain(name: str, ticker: str, model_dna: str, weights: str, training_steps: int = 0,
                      accumulated_trades: int = 0, accumulated_pnl: float = 0.0,
                      accumulated_pnl_percent: float = 0.0, accumulated_wins: int = 0):
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute(
            """
            INSERT INTO policy_brains (
                name, ticker, model_dna, weights, created_at, training_steps,
                accumulated_trades, accumulated_pnl, accumulated_pnl_percent, accumulated_wins
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(name, ticker) DO UPDATE SET
                weights = excluded.weights,
                model_dna = excluded.model_dna,
                training_steps = excluded.training_steps,
                accumulated_trades = excluded.accumulated_trades,
                accumulated_pnl = excluded.accumulated_pnl,
                accumulated_pnl_percent = excluded.accumulated_pnl_percent,
                accumulated_wins = excluded.accumulated_wins
            """,
            (name, ticker, model_dna, weights, time.time(), training_steps,
             accumulated_trades, accumulated_pnl, accumulated_pnl_percent, accumulated_wins)
        )
        conn.commit()
        return True
    except Exception as e:
        logging.error(f"Error saving policy brain {name}: {e}")
        return False
    finally:
        conn.close()

def load_policy_brain(name: str, ticker: str):
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT weights, model_dna, training_steps, accumulated_trades, accumulated_pnl, accumulated_pnl_percent, accumulated_wins FROM policy_brains WHERE name = ? AND ticker = ?", (name, ticker))
        row = cursor.fetchone()
        if row:
            return {
                "weights": row[0], 
                "model_dna": row[1], 
                "training_steps": row[2] if row[2] is not None else 0,
                "accumulated_trades": row[3] if row[3] is not None else 0,
                "accumulated_pnl": row[4] if row[4] is not None else 0.0,
                "accumulated_pnl_percent": row[5] if row[5] is not None else 0.0,
                "accumulated_wins": row[6] if row[6] is not None else 0
            }
        return None
    except Exception as e:
        logging.error(f"Error loading policy brain {name}: {e}")
        return None
    finally:
        conn.close()

def list_policy_brains(ticker: str):
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT name, model_dna, created_at, training_steps, accumulated_trades, accumulated_pnl, accumulated_pnl_percent, accumulated_wins FROM policy_brains WHERE ticker = ? ORDER BY created_at DESC", (ticker,))
        rows = cursor.fetchall()
        return [{
            "name": r[0], 
            "model_dna": r[1], 
            "created_at": r[2], 
            "training_steps": r[3] if r[3] is not None else 0,
            "accumulated_trades": r[4] if r[4] is not None else 0,
            "accumulated_pnl": r[5] if r[5] is not None else 0.0,
            "accumulated_pnl_percent": r[6] if r[6] is not None else 0.0,
            "accumulated_wins": r[7] if r[7] is not None else 0
        } for r in rows]
    except Exception as e:
        logging.error(f"Error listing policy brains: {e}")
        return []
    finally:
        conn.close()

def delete_policy_brain(name: str, ticker: str):
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("DELETE FROM policy_brains WHERE name = ? AND ticker = ?", (name, ticker))
        conn.commit()
        return True
    except Exception as e:
        logging.error(f"Error deleting policy brain {name}: {e}")
        return False
    finally:
        conn.close()

