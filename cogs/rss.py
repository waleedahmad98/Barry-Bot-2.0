import asyncio
import json
import logging
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import discord
import feedparser
from discord import app_commands
from discord.ext import commands, tasks

from utils.auth import require_auth
from utils.helpers import truncate
from utils.qbit import QBitClient

log = logging.getLogger('mediabot.rss')

_STATE_FILE = Path('data/rss_state.json')


def _load_feeds() -> list[dict]:
    if _STATE_FILE.exists():
        return json.loads(_STATE_FILE.read_text()).get('feeds', [])
    return []


def _save_feeds(feeds: list[dict]):
    _STATE_FILE.write_text(json.dumps({'feeds': feeds}, indent=2, default=str))


def _entry_url(entry) -> Optional[str]:
    """Extract a magnet link or torrent URL from an RSS entry."""
    for link in entry.get('links', []):
        t = link.get('type', '')
        if 'bittorrent' in t or 'magnet' in t:
            return link.get('href')
    raw = entry.get('link', '')
    if raw.startswith(('magnet:', 'http')):
        return raw
    return None


class RSS(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self._qbit: Optional[QBitClient] = None

    async def cog_load(self):
        interval = self.bot.config.get('rss', {}).get('check_interval', 30)
        self.check_feeds.change_interval(minutes=interval)
        self.check_feeds.start()

    def cog_unload(self):
        self.check_feeds.cancel()

    async def _build_qbit(self) -> Optional[QBitClient]:
        if self._qbit is None:
            cfg = self.bot.config.get('qbittorrent', {})
            if cfg:
                client = QBitClient(
                    host=cfg.get('host', 'http://localhost'),
                    port=int(cfg.get('port', 8080)),
                    username=cfg.get('username', 'admin'),
                    password=cfg.get('password', 'adminadmin'),
                )
                if await client.connect():
                    self._qbit = client
        return self._qbit

    @tasks.loop(minutes=30)
    async def check_feeds(self):
        feeds = _load_feeds()
        if not feeds:
            return
        qbit = await self._build_qbit()
        if not qbit:
            return

        paths = self.bot.config.get('paths', {})
        changed = False

        for feed in feeds:
            try:
                new_titles = await self._process_feed(feed, qbit, paths)
            except Exception as exc:
                log.error(f'RSS feed "{feed["name"]}" error: {exc}')
                continue

            if new_titles:
                changed = True
                await self._notify(feed['name'], new_titles)

        if changed:
            _save_feeds(feeds)

    @check_feeds.before_loop
    async def _before_check(self):
        await self.bot.wait_until_ready()

    async def _process_feed(
        self, feed: dict, qbit: QBitClient, paths: dict
    ) -> list[str]:
        parsed = await asyncio.to_thread(feedparser.parse, feed['url'])
        seen: set[str] = set(feed.get('seen_guids', []))
        keywords = [k.lower() for k in feed.get('keywords', [])]
        save_path = feed.get('save_path') or paths.get(feed.get('category', 'downloads'))

        downloaded: list[str] = []
        for entry in parsed.entries:
            guid = entry.get('id') or entry.get('link') or entry.get('title', '')
            if guid in seen:
                continue
            seen.add(guid)

            title = entry.get('title', '')
            if keywords and not any(kw in title.lower() for kw in keywords):
                continue

            url = _entry_url(entry)
            if not url:
                continue

            success = await qbit.add_torrent(url, save_path=save_path)
            if success:
                log.info(f'RSS auto-downloaded: {title}')
                downloaded.append(title)

        feed['seen_guids'] = list(seen)
        feed['last_checked'] = datetime.now(timezone.utc).isoformat()
        return downloaded

    async def _notify(self, feed_name: str, titles: list[str]):
        channel_id = self.bot.config.get('discord', {}).get('notify_channel')
        if not channel_id:
            return
        channel = self.bot.get_channel(int(channel_id))
        if not channel:
            return
        body = '\n'.join(f'- {truncate(t, 100)}' for t in titles)
        embed = discord.Embed(
            title=f'RSS: {feed_name}',
            description=f'Downloaded {len(titles)} new item(s):\n{body}',
            color=discord.Color.green(),
        )
        await channel.send(embed=embed)

    # ── Commands ───────────────────────────────────────────────────────────────

    @commands.hybrid_group(name='rss', description='Manage RSS auto-download feeds', invoke_without_command=True)
    @require_auth()
    async def rss(self, ctx: commands.Context):
        await ctx.send_help(ctx.command)

    @rss.command(name='add', description='Add an RSS feed for automatic downloading')
    @app_commands.describe(
        url='RSS feed URL',
        name='Display name',
        category='Where to save: shows, movies, or downloads',
        keywords='Comma-separated keywords to filter entries (empty = download all)',
        save_path='Override the default save path for this feed',
    )
    @require_auth()
    async def rss_add(
        self,
        ctx: commands.Context,
        url: str,
        name: str,
        category: str = 'shows',
        keywords: str = '',
        save_path: str = '',
    ):
        feeds = _load_feeds()
        feed = {
            'id': str(uuid.uuid4())[:8],
            'name': name,
            'url': url,
            'category': category,
            'keywords': [k.strip() for k in keywords.split(',') if k.strip()],
            'save_path': save_path.strip() or None,
            'added_by': ctx.author.id,
            'added_at': datetime.now(timezone.utc).isoformat(),
            'seen_guids': [],
            'last_checked': None,
        }
        feeds.append(feed)
        _save_feeds(feeds)

        embed = discord.Embed(title='RSS feed added', color=discord.Color.green())
        embed.add_field(name='ID', value=feed['id'], inline=True)
        embed.add_field(name='Name', value=name, inline=True)
        embed.add_field(name='Category', value=category, inline=True)
        if feed['keywords']:
            embed.add_field(name='Keywords', value=', '.join(feed['keywords']), inline=False)
        embed.add_field(name='URL', value=truncate(url, 100), inline=False)
        await ctx.send(embed=embed)

    @rss.command(name='list', description='List configured RSS feeds')
    @require_auth()
    async def rss_list(self, ctx: commands.Context):
        feeds = _load_feeds()
        if not feeds:
            await ctx.send('No RSS feeds configured. Add one with `/rss add`.')
            return

        embed = discord.Embed(title=f'RSS Feeds ({len(feeds)})', color=discord.Color.blue())
        for feed in feeds:
            last = feed.get('last_checked')
            last_str = last[:16] if last else 'Never'
            kw_str = ', '.join(feed['keywords']) if feed.get('keywords') else 'All items'
            embed.add_field(
                name=f'[{feed["id"]}] {feed["name"]}',
                value=(
                    f'Category: {feed["category"]} | Keywords: {kw_str}\n'
                    f'Last checked: {last_str}'
                ),
                inline=False,
            )
        await ctx.send(embed=embed)

    @rss.command(name='remove', description='Remove an RSS feed')
    @app_commands.describe(feed_id='Feed ID from /rss list')
    @require_auth()
    async def rss_remove(self, ctx: commands.Context, feed_id: str):
        feeds = _load_feeds()
        new_feeds = [f for f in feeds if f['id'] != feed_id]
        if len(new_feeds) == len(feeds):
            await ctx.send(f'No feed with ID `{feed_id}`. Check `/rss list`.')
            return
        _save_feeds(new_feeds)
        await ctx.send(f'Removed feed `{feed_id}`.')

    @rss.command(name='check', description='Manually trigger an RSS check right now')
    @require_auth()
    async def rss_check(self, ctx: commands.Context):
        await ctx.defer()
        feeds = _load_feeds()
        if not feeds:
            await ctx.send('No feeds configured.')
            return
        await ctx.send('Checking feeds…')
        await self.check_feeds()
        await ctx.send('Done.')


async def setup(bot: commands.Bot):
    await bot.add_cog(RSS(bot))
