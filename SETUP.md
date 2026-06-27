# Media Bot — Setup & Usage

A Discord bot for managing torrents, Plex, and RSS downloads from your phone.

---

## Prerequisites

- Python 3.11+
- [qBittorrent](https://www.qbittorrent.org/) with Web UI enabled
- [Jackett](https://github.com/Jackett/Jackett) or [Prowlarr](https://prowlarr.com/) (optional — needed for `!search`)
- [Plex Media Server](https://www.plex.tv/) (optional — needed for `!movies` / `!shows`)

---

## 1. Create a Discord Bot

1. Go to <https://discord.com/developers/applications> and click **New Application**.
2. Name it (e.g. *MediaBot*), then open the **Bot** tab.
3. Click **Reset Token** and copy the token — this goes in `config.yaml`.
4. Under **Privileged Gateway Intents**, enable **Message Content Intent**.
5. Open **OAuth2 → URL Generator**:
   - Scopes: `bot`, `applications.commands`
   - Bot Permissions: `Send Messages`, `Embed Links`, `Read Message History`
6. Open the generated URL in your browser and invite the bot to your server.

**Get your user ID** (to set as `owner_id`):
- In Discord: Settings → Advanced → Enable Developer Mode.
- Right-click your own name anywhere → **Copy User ID**.

---

## 2. Install Dependencies

```bash
cd ~/Bot
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

---

## 3. Configure `config.yaml`

Open `config.yaml` and fill in each section:

### Discord (required)

```yaml
discord:
  token: "paste-your-bot-token-here"
  prefix: "!"
  owner_id: 123456789          # your Discord user ID
  notify_channel: null         # optional: channel ID for RSS notifications
```

### qBittorrent (required for downloads)

Enable the Web UI in qBittorrent: Tools → Options → Web UI → Enable.

```yaml
qbittorrent:
  host: "http://localhost"
  port: 8080
  username: "admin"
  password: "your-password"
```

### Download paths

Set these to wherever your media lives on disk:

```yaml
paths:
  movies: "/media/movies"
  shows: "/media/shows"
  downloads: "/media/downloads"   # catch-all / unsorted
```

### Plex (optional)

Get your Plex token:
1. Open Plex Web, play any item.
2. In the URL bar you'll see `X-Plex-Token=XXXXXX` — copy that value.
   Or: <https://support.plex.tv/articles/204059436-finding-an-authentication-token-x-plex-token/>

```yaml
plex:
  host: "http://localhost"
  port: 32400
  token: "your-plex-token"
  movies_section: "Movies"     # must match the library name in Plex exactly
  shows_section: "TV Shows"
```

### Jackett (optional — needed for `!search`)

1. Install Jackett: <https://github.com/Jackett/Jackett#installation-on-linux>
2. Open <http://localhost:9117>, add your preferred indexers.
3. Copy the **API Key** from the Jackett dashboard.

```yaml
indexer:
  type: "jackett"
  host: "http://localhost"
  port: 9117
  api_key: "your-jackett-api-key"
```

For Prowlarr, change `type` to `prowlarr` and `port` to `9696`.

### RSS interval

```yaml
rss:
  check_interval: 30    # minutes between automatic checks
```

---

## 4. Run the Bot

```bash
source venv/bin/activate
python bot.py
```

**First run only** — register slash commands with Discord:

```
!sync
```

This only needs to be done once (or after adding new commands).

---

## 5. Run as a Service (Linux)

Create `/etc/systemd/system/mediabot.service`:

```ini
[Unit]
Description=Discord Media Bot
After=network.target

[Service]
Type=simple
User=your-linux-username
WorkingDirectory=/home/your-linux-username/Bot
ExecStart=/home/your-linux-username/Bot/venv/bin/python bot.py
Restart=on-failure
RestartSec=10

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl daemon-reload
sudo systemctl enable mediabot
sudo systemctl start mediabot

# Check logs
journalctl -u mediabot -f
```

---

## 6. Allow Other Users

By default only you (the `owner_id`) can use the bot.

```
!allow @friend       — give someone access
!deny @friend        — remove their access
!allowed             — list everyone who has access
```

You can also pre-add users to `config.yaml` under `allowed_users`:

```yaml
allowed_users:
  - 987654321
```

---

## 7. Command Reference

### Torrents

| Command | Description |
|---|---|
| `!search <query> [movies\|shows\|all]` | Search indexer → pick from dropdown → pick save folder |
| `!download <magnet or URL> [movies\|shows\|downloads]` | Add directly to qBittorrent |
| `!downloads` | List active and completed downloads |
| `!dl_pause <name>` | Pause a torrent (partial name match) |
| `!dl_resume <name>` | Resume a paused torrent |
| `!dl_remove <name> [True]` | Remove a torrent; add `True` to also delete files |

### Plex Library

| Command | Description |
|---|---|
| `!movies [query]` | List all movies, or search by title |
| `!shows [query]` | List all TV shows, or search by title |
| `!recent` | Show recently added media |

### RSS Auto-Download

| Command | Description |
|---|---|
| `!rss add <url> <name> [category] [keywords] [save_path]` | Add a feed |
| `!rss list` | Show all configured feeds and their last check time |
| `!rss remove <id>` | Remove a feed by its ID |
| `!rss check` | Trigger an immediate check right now |

**RSS example — auto-download a show:**

```
!rss add https://showrss.info/show/123.rss "Severance" shows "Severance" /media/shows/Severance
```

- `keywords` filters by title (comma-separated). Leave empty to grab everything in the feed.
- `save_path` overrides the category default path for this specific feed.

### Admin

| Command | Description |
|---|---|
| `!allow @user` | Add a user to the allowlist |
| `!deny @user` | Remove a user |
| `!allowed` | List all allowed users |
| `!status` | Show configured services at a glance |
| `!reload <cog>` | Reload a cog without restarting (owner only) |
| `!sync` | Re-sync slash commands with Discord (owner only) |
| `!ping` | Check bot latency |

All commands work as both `!prefix` and `/slash` commands.

---

## 8. Adding New Features

The bot is built with cogs — each feature is a self-contained file in `cogs/`. To add a new automation:

1. Create `cogs/myfeature.py` following the pattern of any existing cog.
2. Add it to the `cogs` list in `bot.py`:
   ```python
   for cog in ('cogs.torrents', 'cogs.library', 'cogs.rss', 'cogs.admin', 'cogs.myfeature'):
   ```
3. Reload without restarting: `!reload myfeature`

---

## Troubleshooting

**Bot not responding to commands**
- Check the token in `config.yaml` is correct.
- Make sure **Message Content Intent** is enabled in the developer portal.
- Verify you ran `!sync` to register slash commands.

**Search not working**
- Confirm Jackett/Prowlarr is running and at least one indexer is configured.
- Test the API key by opening `http://localhost:9117/api/v2.0/indexers/all/results/torznab?apikey=YOUR_KEY&t=search&q=test` in a browser.

**Downloads not starting**
- Check qBittorrent Web UI is enabled and the credentials match `config.yaml`.
- Try opening `http://localhost:8080` in a browser on the device.

**Plex commands not working**
- Confirm the token is correct and the library section names in `config.yaml` match exactly what appears in Plex (case-sensitive).

**RSS not downloading**
- Run `!rss check` to trigger manually and watch the bot logs.
- Make sure the feed URL is reachable from the device running the bot.
- Check that `keywords` aren't too restrictive — try removing them to grab all items.
