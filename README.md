# Media Bot (Base for Barry Bot) — Setup & Usage

A Discord bot for managing torrents, requesting movies/shows, and browsing Plex/Jellyfin from your phone.

---

## Prerequisites

- Python 3.11+
- [qBittorrent](https://www.qbittorrent.org/) with Web UI enabled — the download client everything else hands torrents to
- [Jackett](https://github.com/Jackett/Jackett) or [Prowlarr](https://prowlarr.com/) — indexer proxy used directly by `/search`, and by Radarr/Sonarr for automatic requests
- [Radarr](https://radarr.video/) (optional — needed for `/request_movie`)
- [Sonarr](https://sonarr.tv/) (optional — needed for `/request_show`)
- [Plex Media Server](https://www.plex.tv/) (optional — needed for `/movies` / `/shows`)
- [Jellyfin](https://jellyfin.org/) (optional — needed for `/jf_movies` / `/jf_shows`)

You can run Plex, Jellyfin, both, or neither — same for Radarr/Sonarr vs. the manual `/search` flow. Nothing here is mutually exclusive.

---

## 1. Create a Discord Bot

1. Go to <https://discord.com/developers/applications> and click **New Application**.
2. Name it (e.g. *MediaBot*), then open the **Bot** tab.
3. Click **Reset Token** and copy the token — this goes in `config.yaml`.
4. Open **OAuth2 → URL Generator**:
   - Scopes: `bot`, `applications.commands`
   - Bot Permissions: `Send Messages`, `Embed Links`
5. Open the generated URL in your browser and invite the bot to your server.

This bot is slash-command only (no `!prefix` text commands), so it doesn't need the **Message Content Intent** or `Read Message History` permission.

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
  owner_id: 123456789          # your Discord user ID
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

### Jackett (optional — needed for `/search`)

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

### Radarr (optional — needed for `/request_movie`)

1. Install Radarr: <https://wiki.servarr.com/radarr/installation>
2. In Radarr, go to **Settings → Indexers** and add Jackett/Prowlarr as an indexer, and **Settings → Download Clients** and add qBittorrent — Radarr needs its own indexer/download-client hookup so it can search and grab automatically once you request something.
3. Note the **Quality Profile** name you want new requests to use (**Settings → Profiles**) and the **Root Folder** path (**Settings → Media Management**) — these must match your config exactly.
4. Copy the **API Key** from **Settings → General**.

```yaml
radarr:
  host: "http://localhost"
  port: 7878
  api_key: "your-radarr-api-key"
  quality_profile: "HD-1080p"     # must match a profile name in Radarr exactly
  root_folder: "/movies"          # must match a root folder configured in Radarr exactly
```

### Sonarr (optional — needed for `/request_show`)

Same idea as Radarr, for TV:

1. Install Sonarr: <https://wiki.servarr.com/sonarr/installation>
2. Hook up Jackett/Prowlarr as an indexer and qBittorrent as a download client in Sonarr too.
3. Note the Quality Profile name and Root Folder path.
4. Copy the API Key from **Settings → General**.

```yaml
sonarr:
  host: "http://localhost"
  port: 8989
  api_key: "your-sonarr-api-key"
  quality_profile: "HD-1080p"     # must match a profile name in Sonarr exactly
  root_folder: "/shows"           # must match a root folder configured in Sonarr exactly
```

Requests made through `/request_movie` and `/request_show` monitor the item and trigger an automatic search in Radarr/Sonarr — the bot doesn't touch qBittorrent directly for these; Radarr/Sonarr do that themselves using the indexer/download-client setup above. The bot's `/search` and `/download` commands remain a separate, manual path for one-off torrents that aren't a "monitor this permanently" request.

#### Download/import notifications (optional)

Barry Bot only posts a notification when a request is *placed* (a "Requested by …" card) — it has no visibility into what happens in Radarr/Sonarr afterwards. To get a message when something actually finishes downloading and gets imported, use Radarr/Sonarr's **own** built-in Discord notifications (no bot config involved):

1. In Discord, go to the channel you want notifications in → **Edit Channel → Integrations → Webhooks → New Webhook**. Copy its **Webhook URL**.
2. In Radarr, go to **Settings → Connect → + → Discord**. Paste the webhook URL, give it a name, and under **Notification Triggers** check **only "On File Import" / "On Import Complete"**. Leave **"On Movie Added"** and **"On Grab"** unchecked — the bot's own request card already covers "someone requested this," and "On Grab" just means a download started, not that it's actually available yet. Save.
3. Repeat step 2 in Sonarr with its own **Settings → Connect → Discord** entry (its equivalent trigger is **"On Import"**, with **"On Series Add"** and **"On Grab"** left unchecked) — Radarr and Sonarr each need this configured separately, and you can point them at the same webhook URL or different channels.

With only the import trigger enabled, you get exactly two messages per request: the bot's "Requested by …" card up front, and Radarr/Sonarr's own import notification once it's actually downloaded and available — no duplicate "added" message in between. These import messages come from Radarr/Sonarr directly (their own username/avatar and formatting), separate from Barry Bot's request card — that's expected, since it's Radarr/Sonarr reporting on their own work rather than the bot.

### Jellyfin (optional)

Get an API key and your user ID:
1. In Jellyfin, go to **Dashboard → API Keys → +** and create a new key.
2. Go to **Dashboard → Users**, click your admin user, and copy the ID from the page URL (`.../userdetails?userId=XXXXXX`).

```yaml
jellyfin:
  host: "http://localhost"
  port: 8096
  api_key: "your-jellyfin-api-key"
  user_id: "your-jellyfin-user-id"
```

Jellyfin's commands (`/jf_movies`, `/jf_shows`, `/jf_recent`) are separate from Plex's (`/movies`, `/shows`, `/recent`) — run one or both side by side without either interfering with the other.

---

## 4. Run the Bot

```bash
source venv/bin/activate
python bot.py
```

Slash commands are registered with Discord automatically on every startup — no manual step needed. If you add new commands while the bot is running, use `/sync` to re-register them without a restart.

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
/allow @friend       — give someone access
/deny @friend        — remove their access
/allowed             — list everyone who has access
```

You can also pre-add users to `config.yaml` under `allowed_users`:

```yaml
allowed_users:
  - 987654321
```

---

## 7. Command Reference

> **Privacy note:** This bot is slash-command only. All bot replies (search results, dropdowns, status messages, etc.) are private/ephemeral — only visible to the person who ran the command, so the channel doesn't get cluttered. The one exception: once a download actually starts or a request is placed, the bot posts a short public notification to the channel — a plain "📥 @user started a download: **Title**" line for torrent downloads, or a "Requested by …" card (poster, title, overview) for `/request_movie` / `/request_show` — so everyone can see what's being grabbed.

### Torrents

| Command | Description |
|---|---|
| `/search <query> [movies\|shows\|all]` | Search indexer → pick from dropdown → pick save folder |
| `/download <magnet or URL> [movies\|shows\|downloads]` | Add directly to qBittorrent |
| `/downloads` | List active and completed downloads |
| `/dl_pause <name>` | Pause a torrent (partial name match) |
| `/dl_resume <name>` | Resume a paused torrent |
| `/dl_remove <name> [True]` | Remove a torrent; add `True` to also delete files |
| `/delete_from_disk <title> [movies\|shows]` | Delete a movie or show downloaded via `/search`/`/download` from disk |

`/delete_from_disk` looks directly at the top-level files/folders under `paths.movies`/`paths.shows` (`category` picks which, defaults to `movies`), matches by partial name, and asks for confirmation before deleting — no Plex, Jellyfin, Radarr, or Sonarr involved. Use this for anything grabbed manually through `/search`/`/download`; use `/remove_movie`/`/remove_show` instead for anything that went through a Radarr/Sonarr request.

### Requests (Radarr / Sonarr)

| Command | Description |
|---|---|
| `/request_movie <query>` | Search TMDB via Radarr → pick from dropdown → monitors it and searches automatically |
| `/request_show <query>` | Search TVDB via Sonarr → pick from dropdown → pick season(s) → monitors and searches automatically |
| `/remove_movie <title> [delete_files]` | Remove a movie from Radarr; deletes its files too unless `delete_files:False` |
| `/remove_show <title> [delete_files]` | Remove a show from Sonarr; deletes its files too unless `delete_files:False` |

Picking a result adds it to Radarr/Sonarr with the quality profile and root folder from `config.yaml`, turns on monitoring, and kicks off an automatic search — Radarr/Sonarr handle finding and grabbing the torrent themselves from there. If it's already in Radarr/Sonarr, the bot tells you instead of adding a duplicate.

For shows, picking a title with more than one season shows a second dropdown to choose which season(s) to monitor — leave "All seasons" selected for the whole series, or pick one or more specific seasons (multi-select) to request just those. Shows with only one season skip straight to adding, since there's nothing to choose between. This is season-level only — Sonarr's own UI is still the place to monitor/search individual episodes.

`/remove_movie` and `/remove_show` match by partial title (same "be more specific" behavior as the torrent commands if more than one matches), then ask for confirmation before actually removing anything. This is the only removal path in the bot — deleting is always routed through Radarr/Sonarr so monitoring is turned off at the same time the files go, instead of leaving something that Radarr/Sonarr will just re-download on its next search.

### Plex Library

| Command | Description |
|---|---|
| `/movies [query]` | List all movies, or search by title |
| `/shows [query]` | List all TV shows, or search by title |
| `/recent` | Show recently added media |

### Jellyfin Library

| Command | Description |
|---|---|
| `/jf_movies [query]` | List all movies, or search by title |
| `/jf_shows [query]` | List all TV shows, or search by title |
| `/jf_recent` | Show recently added media |

Both library sections are browse-only — to remove something, use `/remove_movie` / `/remove_show` (Requests section above), which removes it from Radarr/Sonarr and deletes the files, keeping monitoring state in sync with what's actually on disk.

### Admin

| Command | Description |
|---|---|
| `/allow @user` | Add a user to the allowlist |
| `/deny @user` | Remove a user |
| `/allowed` | List all allowed users |
| `/status` | Show configured services at a glance |
| `/reload <cog>` | Reload a cog without restarting (owner only) |
| `/sync` | Re-sync slash commands with Discord (owner only) |
| `/ping` | Check bot latency |

---

## 8. Adding New Features

The bot is built with cogs — each feature is a self-contained file in `cogs/`. To add a new automation:

1. Create `cogs/myfeature.py` following the pattern of any existing cog.
2. Add it to the `cogs` list in `bot.py`:
   ```python
   for cog in ('cogs.torrents', 'cogs.library', 'cogs.jellyfin', 'cogs.requests', 'cogs.admin', 'cogs.myfeature'):
   ```
3. Reload without restarting: `/reload myfeature`

---

## Troubleshooting

**Bot not responding to commands**
- Check the token in `config.yaml` is correct.
- Slash commands sync automatically on startup — check the bot's logs for `Synced N slash command(s)`. If they're still missing in Discord, run `/sync` manually and/or wait a few minutes for Discord's cache to refresh.

**Search not working**
- Confirm Jackett/Prowlarr is running and at least one indexer is configured.
- Test the API key by opening `http://localhost:9117/api/v2.0/indexers/all/results/torznab?apikey=YOUR_KEY&t=search&q=test` in a browser.

**Downloads not starting**
- Check qBittorrent Web UI is enabled and the credentials match `config.yaml`.
- Try opening `http://localhost:8080` in a browser on the device.

**Plex commands not working**
- Confirm the token is correct and the library section names in `config.yaml` match exactly what appears in Plex (case-sensitive).

**Jellyfin commands not working**
- Confirm the API key and `user_id` are correct — `user_id` must be an actual Jellyfin user's ID (usually your admin account), not the API key itself.
- Test it directly: `http://localhost:8096/System/Info?api_key=YOUR_KEY` should return JSON, not an error.

**`/request_movie` or `/request_show` failing**
- Check `radarr.api_key` / `sonarr.api_key` and that the bot can reach the host/port.
- `quality_profile` and `root_folder` must match an existing profile name and root folder path *exactly* as configured in Radarr/Sonarr — check **Settings → Profiles** and **Settings → Media Management** there if you get a "not found" error.
- If the request goes through but nothing downloads, the problem is on the Radarr/Sonarr side — check that they have a working indexer (Jackett/Prowlarr) and download client (qBittorrent) configured under their own Settings, since the bot doesn't touch qBittorrent for requests.
