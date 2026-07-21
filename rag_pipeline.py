"""
NexusTrader RAG Pipeline — Retrieval-Augmented Generation for LLaMA.
Gives the local Llama 3.2 3B access to a vector database of:
- Trade history
- Audit reports
- Strategy performance data
- Market analysis docs

Uses sentence-transformers for embeddings + FAISS for vector search.
No GPU required — all runs on CPU.
"""
import os
import json
import sqlite3
import logging
import numpy as np
from typing import List, Dict, Optional, Tuple

logger = logging.getLogger(__name__)

# Paths
DB_PATH = os.path.expanduser("~/.nexustrader/nexustrader.db")
AUDIT_DIR = os.path.join(os.path.dirname(__file__), "..")  # parent of nexustrader
VECTOR_STORE_PATH = os.path.expanduser("~/.nexustrader/rag_vector_store")
EMBEDDING_MODEL = "sentence-transformers/all-MiniLM-L6-v2"  # 22M params, runs on CPU

# Try to import sentence-transformers; fall back gracefully
try:
    from sentence_transformers import SentenceTransformer
    HAVE_EMBEDDER = True
except ImportError:
    HAVE_EMBEDDER = False
    logger.warning("sentence-transformers not installed. Run: pip install sentence-transformers faiss-cpu")

try:
    import faiss
    HAVE_FAISS = True
except ImportError:
    HAVE_FAISS = False
    logger.warning("faiss-cpu not installed. Run: pip install faiss-cpu")


class RAGPipeline:
    """RAG pipeline for NexusTrader knowledge retrieval."""

    def __init__(self):
        self.embedder = None
        self.index = None
        self.documents: List[Dict] = []
        self._loaded = False

    def ensure_embedder(self):
        if not HAVE_EMBEDDER:
            raise ImportError("sentence-transformers not installed")
        if self.embedder is None:
            logger.info(f"Loading embedding model: {EMBEDDING_MODEL}")
            self.embedder = SentenceTransformer(EMBEDDING_MODEL)  # CPU, ~80MB
        return self.embedder

    def _chunk_text(self, text: str, chunk_size: int = 512, overlap: int = 64) -> List[str]:
        """Split text into overlapping chunks for embedding."""
        words = text.split()
        chunks = []
        i = 0
        while i < len(words):
            chunk = " ".join(words[i:i + chunk_size])
            chunks.append(chunk)
            i += chunk_size - overlap
        return chunks

    def _collect_trade_documents(self) -> List[Dict]:
        """Build documents from trade history."""
        docs = []
        try:
            conn = sqlite3.connect(DB_PATH)
            cursor = conn.cursor()
            cursor.execute("""
                SELECT symbol, direction, entry_price, exit_price, pnl,
                       entry_time, exit_time, exit_reason
                FROM trades ORDER BY entry_time DESC LIMIT 20
            """)
            trades = cursor.fetchall()
            conn.close()

            for t in trades:
                symbol, direction, entry, exit_p, pnl, entry_t, exit_t, reason = t
                text = (
                    f"Trade: {symbol} {direction}. "
                    f"Entry: ${entry:.6f} at {entry_t}. "
                    f"Exit: ${exit_p:.6f} at {exit_t}. "
                    f"PnL: ${pnl:+.4f}. "
                    f"Exit reason: {reason}. "
                    f"Outcome: {'WIN' if pnl > 0 else 'LOSS'}."
                )
                docs.append({
                    "text": text,
                    "source": "trade",
                    "symbol": symbol,
                    "pnl": pnl,
                    "direction": direction,
                })

            # Trade summary
            wins = sum(1 for t in trades if t[4] > 0)
            losses = sum(1 for t in trades if t[4] <= 0)
            total_pnl = sum(t[4] for t in trades)
            win_rate = wins / len(trades) * 100 if trades else 0
            summary = (
                f"Trade Summary: {len(trades)} total trades. "
                f"Wins: {wins}. Losses: {losses}. "
                f"Win rate: {win_rate:.1f}%. "
                f"Total PnL: ${total_pnl:+.4f}. "
                f"Average win: ${sum(t[4] for t in trades if t[4] > 0) / max(wins, 1):.4f}. "
                f"Average loss: ${sum(t[4] for t in trades if t[4] <= 0) / max(losses, 1):.4f}."
            )
            docs.append({"text": summary, "source": "trade_summary"})
        except Exception as e:
            logger.warning(f"Failed to collect trade docs: {e}")
        return docs

    def _collect_audit_documents(self) -> List[Dict]:
        """Build documents from audit reports."""
        docs = []
        audit_dir = os.path.expanduser("~/nexustrader")  # on bot VM
        audit_files = ["RISK_AUDIT.md", "QUANT_AUDIT.md", "STRATEGY_PERF_AUDIT.md",
                       "ENTRY_EXIT_AUDIT.md", "INFRA_AUDIT.md"]

        for fname in audit_files:
            fpath = os.path.join(audit_dir, fname)
            if not os.path.exists(fpath):
                continue
            try:
                with open(fpath, "r") as f:
                    content = f.read()
                # Extract key findings sections
                sections = content.split("\n## ")
                for section in sections:
                    if section.strip():
                        docs.append({
                            "text": f"[{fname}] " + section.strip()[:1000],
                            "source": "audit",
                            "file": fname,
                        })
            except Exception as e:
                logger.warning(f"Failed to read {fname}: {e}")
        return docs

    def _collect_strategy_documents(self) -> List[Dict]:
        """Build documents describing active strategies."""
        strategies = [
            "EMA Crossover: Uses 9-period and 21-period exponential moving averages. Generates BUY when fast EMA crosses above slow EMA. Generates SELL when fast EMA crosses below slow EMA. Strength depends on angle of divergence.",
            "ML Random Forest: Trained on 30 features including RSI, MACD, volume, volatility, and price momentum. Outputs probability of upward movement. Weight-capped to prevent over-dominance.",
            "Kalman Filter Trend: 1D Kalman filter estimates true price trend by filtering market noise. BUY when estimated trend slope is positive above threshold. SELL when negative below threshold.",
            "MACD Histogram: Standard MACD(12,26,9). BUY when histogram turns positive and accelerating. SELL when histogram turns negative and accelerating. Confirms trend changes.",
            "VWAP Crossover: Volume-weighted average price as fair value anchor. BUY when price crosses above VWAP with volume confirmation. SELL when price crosses below VWAP.",
            "ATR Breakout: Uses Average True Range(14) for volatility-normalized breakout detection. BUY on upside breakout (price > SMA20 + N*ATR). SELL on downside breakout (price < SMA20 - N*ATR).",
        ]
        for s in strategies:
            docs.append({"text": s, "source": "strategy"})

        # Signal quality analysis (from audits)
        docs.append({
            "text": "Signal Correlation Issue: 6 trend-following strategies produce highly correlated signals (~0.7-0.9 correlation). When trend is wrong, ALL strategies are wrong simultaneously. Only ~3-4 effective independent signals instead of 6. Weight penalty of 0.35 applied for correlation.",
            "source": "audit_finding",
        })
        docs.append({
            "text": "Stop Loss Analysis: Current SL=3x ATR, TP=5x ATR. 8 of 10 trades hit stop loss, suggesting SL is too tight for 1h candle volatility. Projected optimal: SL=4x ATR, TP=6x ATR. Minimum position floor $10 to avoid fee erosion.",
            "source": "audit_finding",
        })
        docs.append({
            "text": "Signal Threshold: Currently 0.50 (from DB). Filters out weak signals. Historical analysis shows threshold 0.35-0.60 range optimal. Below 0.35: too many false entries. Above 0.60: too few trades for $1K/day target.",
            "source": "audit_finding",
        })
        return docs

    def _collect_market_context(self) -> List[Dict]:
        """Build documents with current market context."""
        try:
            conn = sqlite3.connect(DB_PATH)
            cursor = conn.cursor()
            cursor.execute("""
                SELECT key, value FROM settings WHERE key IN (
                    'signal_threshold', 'max_position_size', 'max_drawdown',
                    'trading_mode', 'daily_goal'
                )
            """)
            settings = dict(cursor.fetchall())
            conn.close()

            docs = []
            if settings:
                text = "Current bot configuration: " + ", ".join(
                    f"{k}={v}" for k, v in settings.items()
                )
                docs.append({"text": text, "source": "config"})
            return docs
        except Exception:
            return []

    def build_index(self, force_rebuild: bool = False):
        """Build the vector index from all document sources."""
        os.makedirs(VECTOR_STORE_PATH, exist_ok=True)

        # Collect all documents
        self.documents = []
        self.documents.extend(self._collect_trade_documents())
        self.documents.extend(self._collect_audit_documents())
        self.documents.extend(self._collect_strategy_documents())
        self.documents.extend(self._collect_market_context())

        if not self.documents:
            logger.error("No documents collected for RAG index")
            return False

        logger.info(f"Building RAG index from {len(self.documents)} documents")

        # Generate embeddings
        embedder = self.ensure_embedder()
        texts = [d["text"] for d in self.documents]
        embeddings = embedder.encode(texts, show_progress_bar=False)
        embeddings = np.array(embeddings).astype("float32")

        # Build FAISS index
        dim = embeddings.shape[1]
        self.index = faiss.IndexFlatIP(dim)  # Inner product (cosine similarity on normalized vectors)
        faiss.normalize_L2(embeddings)  # Normalize for cosine similarity
        self.index.add(embeddings)

        # Save to disk
        faiss.write_index(self.index, os.path.join(VECTOR_STORE_PATH, "index.faiss"))
        with open(os.path.join(VECTOR_STORE_PATH, "documents.json"), "w") as f:
            json.dump(self.documents, f)
        with open(os.path.join(VECTOR_STORE_PATH, "metadata.json"), "w") as f:
            json.dump({
                "num_documents": len(self.documents),
                "embedding_dim": dim,
                "model": EMBEDDING_MODEL,
            }, f)

        self._loaded = True
        logger.info(f"RAG index built: {len(self.documents)} docs, dim={dim}")
        return True

    def load_index(self):
        """Load a previously built index from disk."""
        idx_path = os.path.join(VECTOR_STORE_PATH, "index.faiss")
        docs_path = os.path.join(VECTOR_STORE_PATH, "documents.json")

        if not os.path.exists(idx_path) or not os.path.exists(docs_path):
            logger.info("No existing RAG index found, building new one...")
            return self.build_index()

        self.index = faiss.read_index(idx_path)
        with open(docs_path, "r") as f:
            self.documents = json.load(f)

        self.ensure_embedder()
        self._loaded = True
        logger.info(f"RAG index loaded: {len(self.documents)} documents")
        return True

    def query(self, query_text: str, top_k: int = 5) -> List[Dict]:
        """Query the RAG index for relevant context.

        Returns:
            List of dicts with 'text', 'source', 'score' keys
        """
        if not self._loaded:
            self.load_index()

        embedder = self.ensure_embedder()
        query_emb = embedder.encode([query_text], show_progress_bar=False)
        query_emb = np.array(query_emb).astype("float32")
        faiss.normalize_L2(query_emb)

        scores, indices = self.index.search(query_emb, min(top_k, len(self.documents)))

        results = []
        for score, idx in zip(scores[0], indices[0]):
            if idx < 0 or idx >= len(self.documents):
                continue
            doc = self.documents[idx]
            results.append({
                "text": doc["text"],
                "source": doc.get("source", "unknown"),
                "score": float(score),
            })
        return results

    def retrieve_context(self, query_text: str, top_k: int = 5) -> str:
        """Get formatted context string for inclusion in LLaMA prompts."""
        results = self.query(query_text, top_k)
        if not results:
            return ""

        lines = ["## Relevant Context (from RAG)\n"]
        for i, r in enumerate(results, 1):
            lines.append(f"{i}. [{r['source']}] (score: {r['score']:.2f}) {r['text']}")
        return "\n".join(lines)


# Singleton
_rag = None

def get_rag() -> RAGPipeline:
    global _rag
    if _rag is None:
        _rag = RAGPipeline()
    return _rag


def rag_query(prompt: str, top_k: int = 5) -> str:
    """Convenience function: get RAG context for a prompt."""
    try:
        rag = get_rag()
        return rag.retrieve_context(prompt, top_k)
    except Exception as e:
        logger.warning(f"RAG query failed: {e}")
        return ""
