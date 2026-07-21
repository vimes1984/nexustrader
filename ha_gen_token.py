import json, secrets, uuid
from datetime import datetime, timezone

with open("/mnt/data/supervisor/homeassistant/.storage/auth") as f:
    data = json.load(f)

token = secrets.token_hex(64)
jwt_key = secrets.token_hex(64)
token_id = uuid.uuid4().hex

new_token = {
    "id": token_id,
    "user_id": "03ac4c4b04e14481a561f2a9d79371f4",
    "client_id": None,
    "client_name": "OpenClaw Automation",
    "token_type": "long_lived_access_token",
    "created_at": datetime.now(timezone.utc).isoformat(),
    "access_token_expiration": 315360000.0,
    "token": token,
    "jwt_key": jwt_key,
    "version": "2026.7.0"
}

data["data"]["refresh_tokens"].append(new_token)
with open("/mnt/data/supervisor/homeassistant/.storage/auth", "w") as f:
    json.dump(data, f, indent=2)

print("TOKEN:" + token)
