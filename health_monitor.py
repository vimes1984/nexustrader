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
    # Auto-resolve orphaned alerts from previous run
    notification_manager.resolve_alerts_by_category("system", "Trading Stream Orphaned")
    
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
            if dd and hasattr(dd, 'current_pct') and dd.current_pct > 5:
                dd_alerted = notification_manager.get_health_state('drawdown_alerted', '0')
                if dd_alerted != '1':
                    notification_manager.push_alert('warning', 'safety',
                        f'Drawdown: {dd.current_pct:.1f}%',
                        f'Current drawdown at {dd.current_pct:.1f}% (max: {dd.max_pct:.1f}%).')
                    notification_manager.set_health_state('drawdown_alerted', '1')
            else:
                notification_manager.set_health_state('drawdown_alerted', '0')
            
            # Track last trade timestamp
            if trades:
                max_ts = max(t.get('exit_time', 0) for t in trades)
                notification_manager.set_health_state('last_trade_ts', str(max_ts))
            
            # Track bot uptime
            notification_manager.set_health_state('last_health_check', str(now))
            
        except Exception as e:
            logging.error(f'[HEALTH] Monitor error: {e}')
        
        await asyncio.sleep(60)
