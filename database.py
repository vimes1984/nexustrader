import sqlite3
import json
import os
import logging
import time

# Safety singletons (lightweight import, no circular deps)
try:
    from evaluation.singletons import mutation_freeze
except ImportError:
    # Fallback: root-level singletons module
    from singletons import mutation_freeze
from trading_modes import ns as ns_key, MODE_RESEARCH, MODE_LIVE

def get_data_dir():
    home = os.path.expanduser("~")
    data_dir = os.path.join(home, ".nexustrader")
    os.makedirs(data_dir, exist_ok=True)
    return data_dir

DB_FILE = os.path.join(get_data_dir(), "nexustrader.db")
DB_PATH = DB_FILE

def get_db_connection():
    conn = sqlite3.connect(DB_PATH, timeout=30.0)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=30000")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn

def init_db():
    logging.info("Initializing SQLite database...")
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # Check if ticks table needs migration
    try:
        cursor.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name='ticks'")
        tbl = cursor.fetchone()
        if tbl and "symbol" not in (tbl[0] or ""):
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
        if "predicted_win_probability" not in columns:
            logging.info("Migrating trades table: adding predicted_win_probability column...")
            cursor.execute("ALTER TABLE trades ADD COLUMN predicted_win_probability REAL")
        if "expected_value" not in columns:
            logging.info("Migrating trades table: adding expected_value column...")
            cursor.execute("ALTER TABLE trades ADD COLUMN expected_value REAL")
        if "risk_reward_ratio" not in columns:
            logging.info("Migrating trades table: adding risk_reward_ratio column...")
            cursor.execute("ALTER TABLE trades ADD COLUMN risk_reward_ratio REAL")
        if "kelly_fraction" not in columns:
            logging.info("Migrating trades table: adding kelly_fraction column...")
            cursor.execute("ALTER TABLE trades ADD COLUMN kelly_fraction REAL")
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
        brain_name TEXT DEFAULT 'Default Brain',
        PRIMARY KEY (timestamp, ticker)
    )
    """)
    
    # Migrate weights_history table: add brain_name column if missing
    try:
        cursor.execute("PRAGMA table_info(weights_history)")
        wh_cols = [row[1] for row in cursor.fetchall()]
        if "brain_name" not in wh_cols:
            logging.info("Migrating weights_history table: adding brain_name column...")
            cursor.execute("ALTER TABLE weights_history ADD COLUMN brain_name TEXT DEFAULT 'Default Brain'")
    except Exception as e:
        logging.error(f"Error migrating weights_history table: {e}")
    
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
    
    # Create active assets table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS active_assets (
        ticker TEXT PRIMARY KEY,
        is_active INTEGER DEFAULT 1,
        tp_multiplier REAL DEFAULT 2.5,
        sl_multiplier REAL DEFAULT 1.5,
        kelly_ceiling REAL DEFAULT 0.2
    )
    """)
    
    # Create agent optimizations log table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS agent_optimizations (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        timestamp REAL,
        agent TEXT,
        parameter TEXT,
        old_value TEXT,
        new_value TEXT,
        rationale TEXT
    )
    """)
    
    # Create agent runs audit trail table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS agent_runs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        timestamp REAL,
        agent TEXT,
        provider TEXT,
        model TEXT,
        prompt TEXT,
        response TEXT,
        status TEXT
    )
    """)
    
    # Create shadow trades table (for testing long-term strategy in shadow mode)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS shadow_trades (
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
        status TEXT,
        tp_price REAL,
        sl_price REAL,
        atr_at_entry REAL
    )
    """)
    
    # Pre-populate and migrate default tickers
    default_tickers = ['ETH-USD', 'SOL-USD', 'BTC-USD', 'DOGE-USD', 'XRP-USD', 'LINK-USD', 'LTC-USD', 'AVAX-USD', 'ADA-USD', 'DOT-USD']
    for t in default_tickers:
        try:
            cursor.execute("INSERT OR IGNORE INTO active_assets (ticker, is_active) VALUES (?, 1)", (t,))
        except Exception:
            pass
            
    # Create indexes for performance
    try:
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_ticks_symbol ON ticks(symbol)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_ticks_timestamp ON ticks(timestamp)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_trades_symbol ON trades(symbol)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_trades_exit_time ON trades(exit_time)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_trades_policy_brain ON trades(policy_brain)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_weights_history_ticker ON weights_history(ticker)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_weights_history_ticker_ts ON weights_history(ticker, timestamp)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_settings_key ON settings(key)")
    except Exception as e:
        logging.error(f"Error creating indexes: {e}")
    
    # Commit and close
    conn.commit()
    conn.close()
    logging.info("Database initialized successfully.")

def save_weights_history(timestamp: float, ticker: str, weights: dict, brain_name: str = 'Default Brain'):
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute(
            "INSERT OR REPLACE INTO weights_history (timestamp, ticker, weights, brain_name) VALUES (?, ?, ?, ?)",
            (timestamp, ticker, json.dumps(weights), brain_name)
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
            "SELECT timestamp, weights, brain_name FROM weights_history WHERE ticker = ? ORDER BY timestamp ASC LIMIT ?",
            (ticker, limit)
        )
        rows = cursor.fetchall()
        conn.close()
        result = []
        for r in rows:
            try:
                w = json.loads(r[1]) if r[1] else {}
            except (json.JSONDecodeError, TypeError):
                w = {}
            result.append({
                "timestamp": r[0],
                "weights": w,
                "brain_name": r[2] if len(r) > 2 else 'Default Brain'
            })
        return result
    except Exception as e:
        logging.error(f"Error loading weights history: {e}")
        return []

def save_tick(row, symbol):
    """Saves a price tick to database."""
    if hasattr(row, "keys") and not isinstance(row, dict):
        row = dict(row)
    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("""
        INSERT OR REPLACE INTO ticks 
        (timestamp, symbol, open, high, low, close, volume, rsi, macd, macd_signal, bb_upper, bb_lower, atr)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            str(row.get('timestamp', '')),
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
        if conn:
            conn.close()

def save_trade(trade):
    """Saves a closed trade to database."""
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        signals_str = json.dumps(trade.get('strategy_signals', []))
        sources_str = json.dumps(trade.get('sentiment_sources', {}))
        # Ensure calibration columns exist (load_calibration_from_trades has ALTER TABLE fallbacks)
        cursor.execute("""
        INSERT INTO trades (symbol, direction, quantity, entry_price, exit_price, pnl, pnl_percent, exit_reason, entry_time, exit_time, strategy_signals, sentiment_sources, policy_brain, trading_mode, predicted_win_probability, expected_value, risk_reward_ratio, kelly_fraction)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
            trade.get('trading_mode', 'paper'),
            trade.get('predicted_win_probability'),
            trade.get('expected_value'),
            trade.get('risk_reward_ratio'),
            trade.get('kelly_fraction')
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
        numeric_fields = {"pnl", "pnl_percent", "entry_price", "exit_price", "quantity", "entry_time", "exit_time", "entry_rsi", "exit_rsi", "slippage", "fee"}
        for r in rows:
            trade = dict(r)
            # Convert numeric fields to proper float/int types (SQLite may return str)
            for k in list(trade.keys()):
                if k in numeric_fields:
                    try:
                        trade[k] = float(trade[k]) if k != "entry_time" and k != "exit_time" else float(trade[k])
                    except (ValueError, TypeError):
                        trade[k] = 0.0
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

def log_optimization(agent: str, parameter: str, old_value: str, new_value: str, rationale: str = ""):
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute(
            "INSERT INTO agent_optimizations (timestamp, agent, parameter, old_value, new_value, rationale) VALUES (?, ?, ?, ?, ?, ?)",
            (time.time(), agent, parameter, str(old_value), str(new_value), rationale)
        )
        conn.commit()
    except Exception as e:
        logging.error(f"Error logging agent optimization: {e}")
    finally:
        conn.close()

def load_optimizations(limit: int = 100):
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT id, timestamp, agent, parameter, old_value, new_value, rationale FROM agent_optimizations ORDER BY timestamp DESC LIMIT ?", (limit,))
        rows = cursor.fetchall()
        return [{
            "id": r[0],
            "timestamp": r[1],
            "agent": r[2],
            "parameter": r[3],
            "old_value": r[4],
            "new_value": r[5],
            "rationale": r[6]
        } for r in rows]
    except Exception as e:
        logging.error(f"Error loading optimizations: {e}")
        return []
    finally:
        conn.close()

def log_agent_run(agent: str, provider: str, model: str, prompt: str, response: str, status: str):
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute(
            "INSERT INTO agent_runs (timestamp, agent, provider, model, prompt, response, status) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (time.time(), agent, provider, model, prompt, response, status)
        )
        conn.commit()
    except Exception as e:
        logging.error(f"Error logging agent run: {e}")
    finally:
        conn.close()

def load_agent_runs(limit: int = 100):
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT id, timestamp, agent, provider, model, prompt, response, status FROM agent_runs ORDER BY timestamp DESC LIMIT ?", (limit,))
        rows = cursor.fetchall()
        return [{
            "id": r[0],
            "timestamp": r[1],
            "agent": r[2],
            "provider": r[3],
            "model": r[4],
            "prompt": r[5],
            "response": r[6],
            "status": r[7]
        } for r in rows]
    except Exception as e:
        logging.error(f"Error loading agent runs: {e}")
        return []
    finally:
        conn.close()

def log_shadow_trade(symbol, direction, quantity, entry_price, status, tp_price, sl_price, atr_at_entry):
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute(
            """
            INSERT INTO shadow_trades (symbol, direction, quantity, entry_price, status, tp_price, sl_price, atr_at_entry, entry_time)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (symbol, direction, quantity, entry_price, status, tp_price, sl_price, atr_at_entry, time.time())
        )
        conn.commit()
    except Exception as e:
        logging.error(f"Error logging shadow trade: {e}")
    finally:
        conn.close()

def update_shadow_trade_exit(trade_id, exit_price, pnl, pnl_percent, exit_reason):
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute(
            """
            UPDATE shadow_trades 
            SET exit_price = ?, pnl = ?, pnl_percent = ?, exit_reason = ?, exit_time = ?, status = 'closed'
            WHERE id = ?
            """,
            (exit_price, pnl, pnl_percent, exit_reason, time.time(), trade_id)
        )
        conn.commit()
    except Exception as e:
        logging.error(f"Error updating shadow trade exit: {e}")
    finally:
        conn.close()

def load_shadow_trades(limit: int = 100):
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute(
            """
            SELECT id, symbol, direction, quantity, entry_price, exit_price, pnl, pnl_percent, exit_reason, entry_time, exit_time, status, tp_price, sl_price, atr_at_entry
            FROM shadow_trades 
            ORDER BY entry_time DESC 
            LIMIT ?
            """,
            (limit,)
        )
        rows = cursor.fetchall()
        return [{
            "id": r[0],
            "symbol": r[1],
            "direction": r[2],
            "quantity": r[3],
            "entry_price": r[4],
            "exit_price": r[5],
            "pnl": r[6],
            "pnl_percent": r[7],
            "exit_reason": r[8],
            "entry_time": r[9],
            "exit_time": r[10],
            "status": r[11],
            "tp_price": r[12],
            "sl_price": r[13],
            "atr_at_entry": r[14]
        } for r in rows]
    except Exception as e:
        logging.error(f"Error loading shadow trades: {e}")
        return []
    finally:
        conn.close()

def _detect_agent_name():
    """Inspect call stack to identify the calling quant agent."""
    import inspect
    import os as _os
    for frame_info in inspect.stack():
        filename = _os.path.basename(frame_info.filename)
        if filename == "self_improvement_agent.py":
            return "PhD Quant Agent"
        elif filename == "nn_agent.py":
            return "NeuralCore Optimizer"
        elif filename == "sentiment_agent.py":
            return "Sentiment Sentinel"
        elif filename == "risk_auditor.py":
            return "Risk Auditor"
        elif filename == "allocator_agent.py":
            return "Ensemble Asset Allocator"
    return None


def save_setting(key, value):
    """Saves system setting (json string or float/int).

    If mutation_freeze is active and the caller is an agent,
    the change is logged as a suggestion and NOT applied.
    """
    old_value = load_setting(key, "")
    agent_name = _detect_agent_name()

    # Check mutation freeze for agent-originated changes
    if agent_name and mutation_freeze.frozen and not key.startswith("prompt_"):
        if str(old_value) != str(value):
            mutation_freeze.suggest(agent_name, key, old_value, value,
                                    reason="Automatic config change blocked by MutationFreeze")
            logging.info("[MutationFreeze] Blocked {} change to {} = {} (was {})".format(
                agent_name, key, value, old_value))
            return  # Don't apply
    
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)", (key, str(value)))
        conn.commit()
    except Exception as e:
        logging.error("Error saving setting {}: {}".format(key, e))
    finally:
        conn.close()
        
    # Log optimization if changed by an agent
    if agent_name and str(old_value) != str(value) and not key.startswith("prompt_"):
        log_optimization(agent_name, key, old_value, value)

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
def save_setting_directly(key, value):
    """Save a setting WITHOUT mutation freeze check or agent logging.
    
    Used by human-approved actions via the dashboard / API.
    Bypasses the inspection-based agent detection in save_setting().
    """
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)", (key, str(value)))
        conn.commit()
    except Exception as e:
        logging.error(f"Error in save_setting_directly {key}: {e}")
    finally:
        conn.close()


# Mode-aware wrappers (trading_modes isolation)
# -------------------------------------------------------------

def save_ns_setting(key, value, mode="paper"):
    """Save a setting key namespaced by trading mode.

    Does NOT trigger mutation freeze or agent logging (by design —
    these are explicit integration calls, not agent-driven changes).
    """
    ns_key_str = ns_key(key, mode)
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)", (ns_key_str, str(value)))
        conn.commit()
    except Exception as e:
        logging.error("Error saving namespaced setting {}: {}".format(ns_key_str, e))
    finally:
        conn.close()


def load_ns_setting(key, mode="paper", default=None):
    """Load a setting key namespaced by trading mode."""
    return load_setting(ns_key(key, mode), default)


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

def load_active_assets():
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT ticker, is_active, tp_multiplier, sl_multiplier, kelly_ceiling FROM active_assets ORDER BY ticker ASC")
        rows = cursor.fetchall()
        return [{
            "ticker": r[0],
            "is_active": bool(r[1]),
            "tp_multiplier": float(r[2]),
            "sl_multiplier": float(r[3]),
            "kelly_ceiling": float(r[4])
        } for r in rows]
    except Exception as e:
        logging.error(f"Error loading active assets: {e}")
        return []
    finally:
        conn.close()

def save_active_asset(ticker: str, is_active: bool, tp_multiplier: float, sl_multiplier: float, kelly_ceiling: float):
    old_active, old_tp, old_sl, old_kelly = True, 2.5, 1.5, 0.2
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT is_active, tp_multiplier, sl_multiplier, kelly_ceiling FROM active_assets WHERE ticker = ?", (ticker,))
        row = cursor.fetchone()
        if row:
            old_active, old_tp, old_sl, old_kelly = bool(row[0]), float(row[1]), float(row[2]), float(row[3])
        
        cursor.execute(
            "INSERT OR REPLACE INTO active_assets (ticker, is_active, tp_multiplier, sl_multiplier, kelly_ceiling) VALUES (?, ?, ?, ?, ?)",
            (ticker, int(is_active), tp_multiplier, sl_multiplier, kelly_ceiling)
        )
        conn.commit()
        
        # Log parameter changes dynamically
        import inspect
        import os
        agent_name = None
        for frame_info in inspect.stack():
            filename = os.path.basename(frame_info.filename)
            if filename == "self_improvement_agent.py":
                agent_name = "PhD Quant Agent"
                break
            elif filename == "nn_agent.py":
                agent_name = "NeuralCore Optimizer"
                break
            elif filename == "sentiment_agent.py":
                agent_name = "Sentiment Sentinel"
                break
            elif filename == "risk_auditor.py":
                agent_name = "Risk Auditor"
                break
            elif filename == "allocator_agent.py":
                agent_name = "Ensemble Asset Allocator"
                break
                
        if agent_name:
            if old_active != is_active:
                log_optimization(agent_name, f"{ticker} Status", "Active" if old_active else "Inactive", "Active" if is_active else "Inactive")
            if old_tp != tp_multiplier:
                log_optimization(agent_name, f"{ticker} TP Mult", f"{old_tp}x", f"{tp_multiplier}x")
            if old_sl != sl_multiplier:
                log_optimization(agent_name, f"{ticker} SL Mult", f"{old_sl}x", f"{sl_multiplier}x")
            if old_kelly != kelly_ceiling:
                log_optimization(agent_name, f"{ticker} Kelly Cap", f"{old_kelly}", f"{kelly_ceiling}")
        return True
    except Exception as e:
        logging.error(f"Error saving active asset {ticker}: {e}")
        return False
    finally:
        conn.close()

def delete_active_asset(ticker: str):
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("DELETE FROM active_assets WHERE ticker = ?", (ticker,))
        conn.commit()
        return True
    except Exception as e:
        logging.error(f"Error deleting active asset {ticker}: {e}")
        return False
    finally:
        conn.close()


def run_db_maintenance():
    """Perform routine database maintenance: trim old data, VACUUM, integrity check."""
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        # Trim old ticks: keep last 100K rows
        tick_count = cursor.execute("SELECT COUNT(*) FROM ticks").fetchone()[0]
        if tick_count > 100000:
            excess = tick_count - 50000
            cursor.execute(
                "DELETE FROM ticks WHERE rowid IN (SELECT rowid FROM ticks ORDER BY timestamp ASC LIMIT ?)",
                (excess,)
            )
            logging.info(f"DB maintenance: trimmed {excess} old tick rows")

        # Trim old portfolio_history: keep last 1 year (8760 hourly entries)
        ph_count = cursor.execute("SELECT COUNT(*) FROM portfolio_history").fetchone()[0]
        if ph_count > 10000:
            cursor.execute(
                "DELETE FROM portfolio_history WHERE timestamp < (SELECT MIN(timestamp) FROM (SELECT timestamp FROM portfolio_history ORDER BY timestamp DESC LIMIT 8760))"
            )
            logging.info(f"DB maintenance: trimmed portfolio_history rows")

        # Trim old agent_runs: keep last 5000
        ar_count = cursor.execute("SELECT COUNT(*) FROM agent_runs").fetchone()[0]
        if ar_count > 5000:
            cursor.execute(
                "DELETE FROM agent_runs WHERE id <= (SELECT id FROM agent_runs ORDER BY id DESC LIMIT 1 OFFSET 5000)"
            )

        # Trim old trades: keep last 1000 closed trades
        # Trades table is unbounded and grows with every closed position.
        # 1000 trades at ~10/day ≈ 100 days of history for backtesting/calibration.
        trade_count = cursor.execute("SELECT COUNT(*) FROM trades").fetchone()[0]
        if trade_count > 1000:
            cursor.execute(
                "DELETE FROM trades WHERE rowid IN ("
                "SELECT rowid FROM trades ORDER BY exit_time ASC LIMIT ?"
                ")",
                (trade_count - 1000,)
            )
            logging.info(f"DB maintenance: trimmed {trade_count - 1000} old trades")

        # Trim old weights_history: keep last 5000 per ticker
        # This table grows with every neural network update (~100/day per ticker)
        try:
            tickers = cursor.execute("SELECT DISTINCT ticker FROM weights_history").fetchall()
            for (ticker_row,) in tickers:
                wh_count = cursor.execute(
                    "SELECT COUNT(*) FROM weights_history WHERE ticker = ?", (ticker_row,)
                ).fetchone()[0]
                if wh_count > 5000:
                    cursor.execute(
                        "DELETE FROM weights_history WHERE ticker = ? AND rowid IN ("
                        "SELECT rowid FROM weights_history WHERE ticker = ? ORDER BY timestamp ASC LIMIT ?"
                        ")",
                        (ticker_row, ticker_row, wh_count - 5000)
                    )
                    logging.debug(f"DB maintenance: trimmed {wh_count - 5000} weights_history rows for {ticker_row}")
        except Exception as e:
            logging.warning(f"DB maintenance: weights_history trim error: {e}")

        conn.commit()
        cursor.execute("PRAGMA integrity_check")
        integrity = cursor.fetchone()[0]
        if integrity == "ok":
            logging.info("DB maintenance: integrity check passed")
        else:
            logging.warning(f"DB maintenance: integrity check result: {integrity}")

        cursor.execute("PRAGMA optimize")
        logging.info("DB maintenance: PRAGMA optimize completed")
    except Exception as e:
        logging.error(f"DB maintenance error: {e}")
    finally:
        conn.close()
