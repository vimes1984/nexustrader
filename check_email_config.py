import sqlite3
import os

db_path = os.path.expanduser("~/.nexustrader/nexustrader.db")
db = sqlite3.connect(db_path)

# Check Proton Bridge config
cursor = db.execute("SELECT key, value FROM settings WHERE key LIKE '%proton%' OR key LIKE '%email%' OR key LIKE '%notif%'")
for row in cursor:
    key, value = row
    if "password" in key.lower():
        print(f"{key}: ****** (exists, len={len(value) if value else 0})")
    else:
        print(f"{key}: {value}")

db.close()
