# Media Bot (Base for Barry Bot) — Setup & Usage

A Discord bot for managing torrents and browsing Plex/Jellyfin from your phone. Movie/show *requests* are handled by a separate companion bot, [Doplarr](#requesting-movies--shows-with-doplarr) — see that section below.

---

## Prerequisites

- Python 3.11+
- [qBittorrent](https://www.qbittorrent.org/) with Web UI enabled — the download client `/search`/`/download` hand torrents to
- [Jackett](https://github.com/Jackett/Jackett) or [Prowlarr](https://prowlarr.com/) — indexer proxy used by `/search`
- [Plex Media Server](https://www.plex.tv/) (optional — needed for `/movies` / `/shows`)
- [Jellyfin](https://jellyfin.org/) (optional — needed for `/jf_movies` / `/jf_shows`)
- [Radarr](https://radarr.video/) / [Sonarr](https://sonarr.tv/) (optional — only needed if you also set up Doplarr for requests; Barry Bot itself doesn't talk to them)

You can run Plex, Jellyfin, both, or neither. Nothing here is mutually exclusive.

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

> **Privacy note:** This bot is slash-command only. All bot replies (search results, dropdowns, status messages, etc.) are private/ephemeral — only visible to the person who ran the command, so the channel doesn't get cluttered. The one exception: once a download actually starts, the bot posts a short public notification to the channel — "📥 @user started a download: **Title**" — so everyone can see what's being grabbed. (Doplarr has its own separate notification behavior for requests — see its section below.)

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

`/delete_from_disk` looks directly at the top-level files/folders under `paths.movies`/`paths.shows` (`category` picks which, defaults to `movies`), matches by partial name, and asks for confirmation before deleting — no Plex, Jellyfin, Radarr, or Sonarr involved. A successful delete is silent (buttons just gray out); you'll only hear from the bot if it fails. Use this only for things grabbed manually through `/search`/`/download` — anything requested through Doplarr belongs to Radarr/Sonarr, so remove it there (or via Doplarr) instead, so monitoring gets turned off along with the files.

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

Both library sections are browse-only — Barry Bot has no removal command. For something grabbed manually via `/search`/`/download`, use `/delete_from_disk`; for anything Radarr/Sonarr manages, remove it from their own UI (or however Doplarr exposes it) so monitoring stays in sync with what's actually on disk.

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
   for cog in ('cogs.torrents', 'cogs.library', 'cogs.jellyfin', 'cogs.admin', 'cogs.myfeature'):
   ```
3. Reload without restarting: `/reload myfeature`

---

## Requesting Movies & Shows with Doplarr

Movie/show requests (search TMDB/TVDB, pick a quality profile, pick seasons, monitor + auto-search in Radarr/Sonarr) aren't a Barry Bot feature — that job is handled by [Doplarr](https://github.com/kiranshila/doplarr_rs), a separate, purpose-built Discord bot that runs alongside Barry Bot as its own process. It needs its **own** Discord application/bot token (Barry Bot's token won't work for it) and its own container.

> This section is based on Doplarr's Rust rewrite (`doplarr_rs`) — the original Clojure version is no longer developed. Config field names can change between releases, so treat `config.example.toml` in that repo as the source of truth if anything here looks out of date.

### 1. Create a second Discord bot

Doplarr needs its own application, separate from Barry Bot's:

1. Go to <https://discord.com/developers/applications> → **New Application** → name it (e.g. *Doplarr*).
2. Open the **Bot** tab → **Reset Token** → copy it.
3. **OAuth2 → URL Generator**: scopes `bot` + `applications.commands`; permission `Send Messages` (only needed if you want public request announcements — see `public_followup` below).
4. Open the generated URL and invite it to the same server as Barry Bot.

### 2. Configure it

Create `config.toml` next to wherever you run Doplarr:

```toml
discord_token = "YOUR_DOPLARR_BOT_TOKEN"

# true = successful requests post publicly in the channel; false = fully ephemeral
public_followup = true

[[backends]]
media = "movie"                 # becomes the slash command: /request movie
[backends.config.Radarr]
url = "http://localhost:7878"
api_key = "your-radarr-api-key"
quality_profile = "HD-1080p"    # optional — omit to let requesters pick at request time
rootfolder = "/movies"          # optional, same idea
minimum_availability = "announced"  # optional: tba | announced | inCinemas | released

[[backends]]
media = "series"                # becomes: /request series
[backends.config.Sonarr]
url = "http://localhost:8989"
api_key = "your-sonarr-api-key"
quality_profile = "HD-1080p"    # optional
rootfolder = "/shows"           # optional
allow_specials = false          # optional: offer Season 0 in the season picker
allow_all_seasons = true        # optional: offer an "All Seasons" option
```

Both `[backends.config.Radarr]`/`[backends.config.Sonarr]` blocks are otherwise identical to what Barry Bot used to need — same API keys, same requirement that `quality_profile`/`rootfolder` match Radarr/Sonarr exactly if you set them. Leaving them out isn't a fallback-to-default like Barry Bot's version was — Doplarr instead asks the requester to pick at request time, every time.

Radarr/Sonarr also still need their own indexer (Jackett/Prowlarr) and download client (qBittorrent) configured under their own Settings — same requirement as before, unrelated to Doplarr or Barry Bot.

Values can pull from environment variables instead of being written in plaintext: `api_key = "${RADARR_API_KEY}"`.

### 3. Run it

```yaml
# docker-compose.yml
services:
  doplarr:
    image: ghcr.io/activexray/doplarr_rs:latest
    container_name: doplarr
    restart: unless-stopped
    volumes:
      - ./config.toml:/config.toml:ro
```

```bash
docker compose up -d
docker compose logs -f doplarr   # confirm it connected and registered /request
```

### Download/import notifications (optional)

Doplarr's own notifications only cover the request being placed (and only if `public_followup = true`) — it has no visibility into what happens in Radarr/Sonarr afterwards, same limitation Barry Bot had. For a message when something actually finishes downloading, use Radarr/Sonarr's own built-in Discord notifications:

1. In Discord: **Edit Channel → Integrations → Webhooks → New Webhook** → copy the URL.
2. In Radarr: **Settings → Connect → + → Discord** → paste the webhook URL → under **Notification Triggers** check **only "On Import"**. Leave "On Movie Added" and "On Grab" unchecked so you don't get a duplicate ping before anything's actually available.
3. Repeat in Sonarr's own **Settings → Connect → Discord** (same idea — only its "On Import" trigger).

### Doplarr Troubleshooting

**`/request` not appearing at all**
- Check `docker compose logs doplarr` for a connection/token error, and that it's using its own bot token, not Barry Bot's.
- New global slash commands can take a few minutes to show up — same client-cache caveat as Barry Bot's commands.

**Request fails or "not found" errors**
- `quality_profile`/`rootfolder`, if set, must match a profile name / root folder path *exactly* as configured in Radarr/Sonarr — check **Settings → Profiles** and **Settings → Media Management** there.
- Confirm `api_key` and that Doplarr's container can actually reach Radarr/Sonarr's `url` (containers on different Docker networks are a common cause).

**Request succeeds but nothing downloads**
- That's a Radarr/Sonarr-side problem, not Doplarr — check they have a working indexer and download client configured under their own Settings.

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

**`/request` not working** — that's Doplarr, a separate bot; see [Doplarr Troubleshooting](#doplarr-troubleshooting) above.
