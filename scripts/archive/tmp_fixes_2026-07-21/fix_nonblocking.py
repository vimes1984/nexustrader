with open("/root/nexustrader/main.py") as f:
    content = f.read()

# Fix the start_stream action to handle already-active gracefully
old_start = '        elif action == "start_stream":\n            orchestrator.start_stream(mode="live", poll_interval=5)\n            return {"status": "ok", "message": "Price stream started in LIVE mode"}\n        \n        else:'

new_start = '        elif action == "start_stream":\n            if getattr(orchestrator, "is_simulating", False):\n                return {"status": "ok", "message": "Price stream is already active."}\n            orchestrator.start_stream(mode="live", poll_interval=5)\n            return {"status": "ok", "message": "Price stream started in LIVE mode"}\n        \n        else:'

content = content.replace(old_start, new_start)

# Also fix toggle_mode to be non-blocking
old_toggle = """        elif action == "toggle_mode":
            current = getattr(ee, "trading_mode", "live")
            new_mode = "simulation" if current == "live" else "live"
            ee.trading_mode = new_mode
            database.save_setting("trading_mode", new_mode)
            if hasattr(ee, "config"):
                ee.config["trading_mode"] = new_mode
            # Restart stream with new mode
            orchestrator.start_stream(mode=new_mode, poll_interval=5)
            logging.info(f"Trading mode toggled: {current} -> {new_mode}")
            return {"status": "ok", "message": f"Switched to {new_mode.upper()} mode. Stream restarted."}"""

new_toggle = """        elif action == "toggle_mode":
            current = getattr(ee, "trading_mode", "live")
            new_mode = "simulation" if current == "live" else "live"
            ee.trading_mode = new_mode
            database.save_setting("trading_mode", new_mode)
            if hasattr(ee, "config"):
                ee.config["trading_mode"] = new_mode
            logging.info(f"Trading mode toggled: {current} -> {new_mode}")
            # Non-blocking restart
            import threading
            threading.Thread(target=lambda: orchestrator.start_stream(mode=new_mode, poll_interval=5), daemon=True).start()
            return {"status": "ok", "message": f"Switched to {new_mode.upper()} mode. Stream restarting."}"""

if old_toggle in content:
    content = content.replace(old_toggle, new_toggle)
    print("OK - toggle_mode made non-blocking")
else:
    # Check what's there
    idx = content.find("action == toggle_mode")
    print("Toggle at", idx)
    print(content[idx:idx+300])

with open("/root/nexustrader/main.py", "w") as f:
    f.write(content)

print("Done")
