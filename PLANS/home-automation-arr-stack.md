# Plan: *arr Stack + Google Home Automation

**Created:** 2026-07-21
**Last Updated:** 2026-07-21 11:30 UTC
**Status:** Phase 1 ✅ | Phase 2 ✅ | Phase 3 ⚠️ needs HA token | Phase 5 ✅ | Phase 6 in progress

---

## 🗺️ Current Landscape

```
┌─────────────────────────────────────────────────────────────┐
│                    192.168.0.0/24 LAN                        │
│                                                              │
│  .1    TP-Link Router (DNS forwarder only — no custom DNS)   │
│  .69   WPsite CT (104) — bumble.cottage WP site, Apache     │
│  .77   chris-System — Home Assistant (SSH blocked/ufw)       │
│  .144  nexustrader bot VM                                    │
│  .166  Proxmox hypervisor                                    │
│  .181  plex CT (102) — *arr suite + Nginx                    │
│  .197  openclaw-server CT (113)                              │
│  .229  OwntoneVM (112) — music + downloaders                 │
│                                                              │
│  .30   launchforge-server CT (114)                           │
│  .??   Pi-hole (being set up by Chris)                       │
└──────────────────────────────────────────────────────────────┘
```

### CT102 "plex" (192.168.0.181) — *arr Suite
| Service    | Port  | Notes                        |
|------------|-------|------------------------------|
| Nginx      | 80    | `media.bcottage` config exists, no DNS |
| Plex       | 32400 | Media server                 |
| Radarr     | 7878  | Movies                       |
| Sonarr     | 8989  | TV shows                     |
| Readarr    | 8787  | Books                        |
| Prowlarr   | 9696  | Indexer manager              |

### VM112 "OwntoneVM" (192.168.0.229) — Music + Downloaders
| Service    | Port  | Notes                        |
|------------|-------|------------------------------|
| OwnTone    | 3688  | HTTP web interface           |
| OwnTone    | 3689  | DAAP (iTunes/AirPlay)       |
| OwnTone    | 6600  | MPD protocol                 |
| Lidarr     | 8686  | Music manager                |
| Deluge     | 8112  | Torrent web UI               |
| SABnzbd    | 5678  | Usenet downloader            |

### CT104 "WPsite" (192.168.0.69) — bumble.cottage
| Service    | Port  | Notes                        |
|------------|-------|------------------------------|
| Apache     | 80,443| WordPress site (password-protected) |
| MariaDB    | 3306  | WP database                  |
| Webmin     | 10000 | Admin panel (stunnel'd)      |

⚠️ WP siteurl/home are set to literally `http:` (broken/incomplete). Needs fixing.

### CT105 "Owntune" — DEAD/EXPENDABLE
- Network interface DOWN, no IP. Can be destroyed and repurposed.

---

## 🎯 Goal Architecture

```
User: "Hey Google, download Inception"
  │
  ▼
Google Home ──► Home Assistant (192.168.0.77) ──► Webhook/API call
  │                                                   │
  │                              ┌────────────────────┘
  │                              ▼
  │                    Radarr API (192.168.0.181:7878)
  │                              │
  │                    Prowlarr searches indexers
  │                              │
  │                    Deluge/SABnzbd downloads
  │                              │
  │                    Plex imports and serves
  │                              ▼
  │                    "Inception is ready, boss!"
  │
  └──► Same flow for music: Google → HA → Lidarr → SABnzbd/Deluge → OwnTone
```

---

## 📋 Implementation Phases

### Phase 1: DNS Foundation (Pi-hole) ✅ COMPLETE
**Completed 2026-07-21**

1. ✅ **Pi-hole running** on Raspberry Pi at 192.168.0.200 (v6.4.3, Raspbian 11)
2. ✅ **Local DNS records added** — all 10 `*.bcottage` domains resolve
3. ✅ **DNS configured on:** Proxmox, CT102 (plex), CT104 (WPsite), VM112 (OwntoneVM)
4. ⚠️ **Router DHCP** still points clients to 192.168.0.1 for DNS — to fully cut over the whole network, either:
   - Set Pi-hole (192.168.0.200) as DNS server in router DHCP settings
   - Or enable Pi-hole's DHCP server and disable router DHCP

> Full details: `PI-HOLE.md`

### Phase 2: Nginx Reverse Proxy (CT102) ✅ COMPLETE
8 reverse proxy vhosts configured on CT102 nginx. Nginx config test passes. All local *arr services proxied perfectly.

| URL | Proxies To | Status |
|-----|-----------|--------|
| radarr.bcottage | 127.0.0.1:7878 | ✅ 200 |
| sonarr.bcottage | 127.0.0.1:8989 | ✅ 200 |
| readarr.bcottage | 127.0.0.1:8787 | ✅ 200 |
| prowlarr.bcottage | 127.0.0.1:9696 | ✅ 200 |
| lidarr.bcottage | 192.168.0.229:8686 | ✅ 200 |
| deluge.bcottage | 192.168.0.229:8112 | ✅ 200 |
| owntone.bcottage | 192.168.0.229:3688 | ⚠️ Slow timeout |
| sabnzbd.bcottage | 192.168.0.229:5678 | ⚠️ 403 (host header) |

### Phase 3: Home Assistant Integration (192.168.0.77)
**Important:** SSH is blocked by ufw on .77 — will need Chris to open port 22 temporarily, or use the HA web UI.

1. **Enable Home Assistant API** (if not already)
2. **Create RESTful commands** in HA to call Radarr/Sonarr/Lidarr APIs:
   - Movie download (Radarr)
   - TV show download (Sonarr)
   - Music/album download (Lidarr)
3. **Create HA scripts/automations** with parameters
4. **Expose to Google Home** via Home Assistant Cloud (Nabu Casa) or manual Google Assistant integration

### Phase 4: Google Home Voice Commands
1. **Define voice commands** in Home Assistant:
   - "Download movie {movie_name}" → Radarr add + search
   - "Download TV show {show_name}" → Sonarr add + search  
   - "Download album {album_name} by {artist}" → Lidarr add + search
   - "What's downloading?" → status check
   - "Is {movie} ready yet?" → Plex check
2. **Google Home routines** for natural language

### Phase 5: bumble.cottage Dashboard ✅ (partial)
1. ✅ **Fixed WP siteurl** — `http://bumble.bcottage` (was broken `http:`)
2. 🔜 **Dashboard widgets** — to be added later

### Phase 6: Cleanup
1. **Destroy CT105 "Owntune"** — dead container, free up resources
2. **Document everything** on bumble.cottage
3. **Set up SSH keys** so OpenClaw can manage all hosts smoothly

---

## ⚠️ Prerequisites from Chris

| What | Why |
|------|-----|
| Pi-hole IP address | Need to add DNS records there |
| SSH access to 192.168.0.77 (HA) | Need to configure Home Assistant (or use web UI) |
| Home Assistant login/API key | For HA configuration |
| Radarr/Sonarr/Lidarr API keys | For service-to-service calls |
| bumble.cottage WP admin password | To fix siteurl and add dashboard |

---

## 🔧 API Endpoints We'll Use

### Radarr (v3 API)
```
POST /api/v3/movie          — Add movie
GET  /api/v3/movie/lookup?term=   — Search movies
POST /api/v3/command        — Trigger search
```

### Sonarr (v3 API)
```
POST /api/v3/series         — Add series
GET  /api/v3/series/lookup?term=  — Search
```

### Lidarr
```
POST /api/v1/artist         — Add artist
GET  /api/v1/search?term=   — Search
```

### SABnzbd
```
GET /api?mode=queue&output=json    — Queue status
GET /api?mode=version              — Health check
```

### Deluge (JSON-RPC)
```
WebUI: http://host:8112/json
```

---

## 🍌 Notes
- All services currently running bare-metal (no Docker), which is fine — means direct config file access
- The `media.bcottage` nginx config already exists on CT102, just needs DNS to work
- OwnTone has Chromecast support built-in — could stream music to Google Home speakers directly
- Can also expose OwnTone to Home Assistant for AirPlay/Chromecast control
- The CT105 "Owntune" has a 200GB disk — could be repurposed as a dedicated download cache or backup target before destroying
