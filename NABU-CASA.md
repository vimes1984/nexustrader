# Nabu Casa CNAME + Google Assistant Setup

## CNAME Records Issue
The CNAMEs Nabu Casa is asking for need to go in your PUBLIC DNS — wherever `bumble.cottage.com` is registered (Namecheap? GoDaddy? Cloudflare?).

**Check:** Does `bumble.cottage.com` actually exist as a public domain? From our DNS check, it doesn't seem to resolve publicly. It might just be your internal `.bcottage` TLD, which wouldn't work for Nabu Casa's SSL verification.

### Option A: Add subdomain to an existing domain you own
If you own another domain (like a personal domain), add the CNAME records there instead of bumble.cottage.com.

### Option B: Use Nabu Casa's built-in domain
You can skip the custom domain and just use Nabu Casa's auto-generated URL (like `xyz.ui.nabu.casa`).

In Nabu Casa settings → Home Assistant Cloud → Remote Access:
- Just enable "Remote Access" without configuring a custom domain
- Nabu Casa gives you a free `*.ui.nabu.casa` URL

## Google Assistant Setup (Where to Find It)

The Google Assistant integration isn't in Nabu Casa's web dashboard — it's in **Home Assistant** itself:

1. Open **Home Assistant** → **Settings**
2. Click **Voice assistants** (microphone icon)
3. At the top right, click **"+ Add Assistant"**
4. Select **Google Assistant**
5. Follow the wizard — Nabu Casa auto-handles the Google Action config

If you don't see "+ Add Assistant":
- Go to **Settings** → **Devices & services** → **Add Integration**
- Search for "Google Assistant" 
- Click it and authorize with your Google account

### Quick Check: Is Nabu Casa Cloud active?
In HA: Settings → Home Assistant Cloud
- You should see a green "Connected" status
- If not, click "Sign in" and authorize

---

## DHCP Reservation
- CT102 is at **192.168.0.49** (reserved on router) ✅
- All HA configs already pointing to .49
- All sensors/commands working
