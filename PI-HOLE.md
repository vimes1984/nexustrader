# Pi-hole Setup — Complete ✅

**Date:** 2026-07-21
**Status:** DONE

## Pi-hole Details

| Field | Value |
|-------|-------|
| **IP** | 192.168.0.200 |
| **Hostname** | raspberrypi |
| **OS** | Raspbian GNU/Linux 11 (bullseye) |
| **Pi-hole version** | Core v6.4.3 / Web v6.6 / FTL v6.7 |
| **Web admin** | http://192.168.0.200:8080/admin or https://192.168.0.200:443/admin |
| **SSH user** | pi |
| **SSH password** | PiHole2026!bcottage |
| **SSH key** | OpenClaw ed25519 key added |
| **Blocking** | ✅ Enabled |
| **Upstream DNS** | 1.1.1.1, 8.8.8.8 |
| **Local domain** | bcottage |
| **Reverse lookup** | Conditional forwarding to router (192.168.0.1) for 192.168.0.0/24 |

## DNS Records Configured (12 total, 1 removed)

| Domain | IP | Service |
|--------|-----|---------|
| bumble.bcottage | 192.168.0.69 | WordPress dashboard |
| openclaw.bcottage | 192.168.0.197 | OpenClaw Gateway |
| nexustrader.bcottage | 192.168.0.144 | NexusTrader bot |
| launchforge.bcottage | 192.168.0.30 | LaunchForge server |
| radarr.bcottage | 192.168.0.181 | Radarr (movies) |
| sonarr.bcottage | 192.168.0.181 | Sonarr (TV) |
| readarr.bcottage | 192.168.0.181 | Readarr (books) |
| prowlarr.bcottage | 192.168.0.181 | Prowlarr (indexers) |
| media.bcottage | 192.168.0.181 | Plex |
| lidarr.bcottage | 192.168.0.229 | Lidarr (music dl) |
| deluge.bcottage | 192.168.0.229 | Deluge (torrents) |
| sabnzbd.bcottage | 192.168.0.229 | SABnzbd (usenet) |

> ~~owntone.bcottage~~ — REMOVED 2026-07-21 (CT105 destroyed)

## Security
- **Web admin password:** REMOVED (no auth required on LAN)
- **SSH:** Key-based only (password changed from default)
- **Web admin ports:** 8080 (HTTP), 443 (HTTPS) |

## Hosts Using Pi-hole for DNS
- Proxmox (192.168.0.166)
- CT102 plex (192.168.0.181)
- CT104 WPsite (192.168.0.69)
- VM112 OwntoneVM (192.168.0.229)

## DHCP Server ❌ DISABLED (per Chris preference)
Router (TP-Link Archer AX53) handles DHCP. Pi-hole is DNS-only.

## Notes
- **Router DHCP reservation needed**: MAC `06:07:DB:0A:FA:9D` → IP `192.168.0.181` on TP-Link Archer AX53 (CT102 currently gets random DHCP IP)
- CT105 (Owntune, 200GB) destroyed 2026-07-21 — freed up storage on hhd1
- CT102 Proxmox firewall disabled to fix network connectivity (was causing no-internet issue)
- Pi-hole web admin uses port 8080 (HTTP) and 443 (HTTPS), not port 80
- Admin password was set during first-time setup — hash stored
- Static IP configured via dhcpcd.conf — survives reboots
