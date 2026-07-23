# health_monitor.py — background task for NexusTrader
import asyncio
import logging
import time
import notification_manager
import database

_health_task = None

async def health_monitor_loop(orchestrator, kill_switch, drawdown_tracker):
    """Periodic health check - runs every 60s and pushes alerts."""
    await asyncio.sleep(15)
    last_orphan_alert = 0
    last_http_warn = 0
    last_watchdog_warn = 0
    # Auto-resolve orphaned alerts from previous run
    notification_manager.resolve_alerts_by_category("system", "Trading Stream Orphaned")
    notification_manager.resolve_alerts_by_category("system", "API Server Unreachable")
    notification_manager.resolve_alerts_by_category("system", "Loop Watchdog")
    
    while True:
        try:
            now = time.time()
            
            # 1. Check if ticker streams are alive (not orphaned)
            streams_alive = False
            for ticker in orchestrator.tickers:
                di = orchestrator.data_ingestions.get(ticker)
                if di and hasattr(di, "streaming") and di.streaming:
                    streams_alive = True
                    break
            
            if not streams_alive and orchestrator.execution_engine.trading_mode == 'live':
                if (now - last_orphan_alert) > 600:
                    title = 'Trading Stream Orphaned'
                    msg = 'No live ticker streams running. Bot is serving API but not processing market data. Restart required.'
                    logging.warning(f'[HEALTH] {title}: {msg}')
                    notification_manager.push_alert('critical', 'system', title, msg)
                    last_orphan_alert = now
            else:
                # Streams came back - auto-resolve orphaned alerts
                notification_manager.resolve_alerts_by_category('system', 'Trading Stream Orphaned')
                last_orphan_alert = 0
            
            # 2. Check for insufficient funds errors
            ee = orchestrator.execution_engine
            if hasattr(ee, 'insufficient_funds_count'):
                ifc = ee.insufficient_funds_count
                prev = int(notification_manager.get_health_state('last_insufficient_count', '0'))
                if ifc > prev:
                    notification_manager.push_alert('warning', 'exchange',
                        'Insufficient Exchange Funds',
                        f'Kraken rejected {ifc} orders with insufficient funds. Cash balance may be too low.')
                    notification_manager.set_health_state('last_insufficient_count', str(ifc))
            
            # 3. Check for extended inactivity
            trades = ee.closed_trades if hasattr(ee, 'closed_trades') else []
            last_trade_ts = 0
            if trades:
                last_trade_ts = max(t.get('exit_time', 0) for t in trades)
            else:
                lt = notification_manager.get_health_state('last_trade_ts', '0')
                last_trade_ts = float(lt) if lt else 0
            
            idle_hours = (now - last_trade_ts) / 3600 if last_trade_ts > 0 else 0
            prev_idle = float(notification_manager.get_health_state('last_idle_alert_hours', '0'))
            
            if idle_hours > 3 and idle_hours > prev_idle + 1:
                ts_str = time.strftime('%Y-%m-%d %H:%M UTC', time.gmtime(last_trade_ts))
                notification_manager.push_alert('warning', 'trading',
                    f'Inactive for {idle_hours:.1f}h',
                    f'No trades closed since {ts_str}.')
                notification_manager.set_health_state('last_idle_alert_hours', str(idle_hours))
            
            # 4. KillSwitch tripped
            ks = kill_switch
            if ks and hasattr(ks, 'tripped') and ks.tripped:
                ks_alerted = notification_manager.get_health_state('killswitch_alerted', '0')
                if ks_alerted != '1':
                    notification_manager.push_alert('critical', 'safety',
                        'KillSwitch Tripped',
                        f'Trading halted. Daily PnL: ${ks.daily_pnl:.2f}. Reason: {ks.trigger_reason or "Unknown"}')
                    notification_manager.set_health_state('killswitch_alerted', '1')
            
            # 5. Drawdown warning
            dd = drawdown_tracker
            if dd and hasattr(dd, 'current_drawdown') and dd.current_drawdown > 0.05:
                dd_alerted = notification_manager.get_health_state('drawdown_alerted', '0')
                if dd_alerted != '1':
                    notification_manager.push_alert('warning', 'safety',
                        f'Drawdown: {dd.current_drawdown*100:.1f}%',
                        f'Current drawdown at {dd.current_drawdown*100:.1f}% (max: {dd.max_drawdown*100:.1f}%).')
                    notification_manager.set_health_state('drawdown_alerted', '1')
            else:
                notification_manager.set_health_state('drawdown_alerted', '0')
            
            # 6. Track tick freshness: find most recent tick across any ticker
            _latest_tick_ts = 0.0
            _tickers = getattr(orchestrator, "tickers", []) or []
            for _t in _tickers:
                _tick = getattr(orchestrator, "latest_ticks", {}).get(_t, None) or {}
                _ts = _tick.get("timestamp", 0) if isinstance(_tick, dict) else 0
                if hasattr(_ts, "timestamp"):
                    _ts = _ts.timestamp()
                try:
                    _ts = float(_ts)
                except (ValueError, TypeError):
                    _ts = 0.0
                if _ts > _latest_tick_ts:
                    _latest_tick_ts = _ts
            
            _tick_idle_sec = int(now - _latest_tick_ts) if _latest_tick_ts > 0 else -1
            
            # 7. Self-probe: check API server is responding on its own port
            try:
                import urllib.request, json as _json
                _url = "http://127.0.0.1:8000/api/health"
                _req = urllib.request.Request(_url, method="GET")
                _resp = urllib.request.urlopen(_req, timeout=3.0)
                _body = _resp.read().decode("utf-8")
                _data = _json.loads(_body)
                if _data.get("status") == "ok":
                    notification_manager.resolve_alerts_by_category("system", "API Server Unreachable")
                    last_http_warn = 0
                else:
                    raise ValueError("unexpected status")
            except Exception as _http_err:
                if last_http_warn == 0 or (now - last_http_warn) > 600:
                    logging.warning(f"[HEALTH] API self-probe FAILED: {_http_err}")
                    notification_manager.push_alert("critical", "system",
                        "API Server Unreachable",
                        f"Self-probe on http://127.0.0.1:8000/api/health failed: {_http_err}. Dashboard will be disconnected.")
                    last_http_warn = now
            
            # 8. Watchdog: check if main loop processed data recently (trade-based + tick-based)
            _last_trade_time = getattr(ee, '_last_trade_time', 0) if ee else 0
            _watchdog_ref = max(_last_trade_time, _latest_tick_ts)
            if _watchdog_ref > 0 and (now - _watchdog_ref) > 60:
                if last_watchdog_warn == 0 or (now - last_watchdog_warn) > 600:
                    _idle_sec = int(now - _watchdog_ref)
                    _tick_idle_str = f"{_tick_idle_sec}s" if _tick_idle_sec >= 0 else "N/A (no ticks yet)"
                    _trade_idle_str = f"{int(now-_last_trade_time)}s" if _last_trade_time > 0 else "N/A"
                    logging.warning(f"[HEALTH] Loop watchdog: idle for {_idle_sec}s (tick_age={_tick_idle_str}, trade_age={_trade_idle_str})")
                    notification_manager.push_alert("warning", "trading",
                        "Main Loop Stalled",
                        f"No market data tick or trade for {_idle_sec}s. tick_age={_tick_idle_str}, trade_age={_trade_idle_str}")
                    last_watchdog_warn = now
            else:
                last_watchdog_warn = 0

            # Track last trade timestamp
            if trades:
                max_ts = max(t.get('exit_time', 0) for t in trades)
                notification_manager.set_health_state('last_trade_ts', str(max_ts))
            
            # Track bot uptime
            notification_manager.set_health_state('last_health_check', str(now))
            
        except Exception as e:
            logging.error(f'[HEALTH] Monitor error: {e}')
        
        await asyncio.sleep(60)
