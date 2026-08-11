from typing import Optional

import discord
from discord import app_commands
from discord.ext import commands

from utils.auth import require_auth
from utils.helpers import truncate
from utils.jellyfin import JellyfinClient, MediaItem


class Jellyfin(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self._jellyfin: Optional[JellyfinClient] = None

    async def _build_jellyfin(self) -> Optional[JellyfinClient]:
        if self._jellyfin is None:
            cfg = self.bot.config.get('jellyfin', {})
            if cfg.get('api_key') and cfg.get('user_id'):
                client = JellyfinClient(
                    host=cfg.get('host', 'http://localhost'),
                    port=int(cfg.get('port', 8096)),
                    api_key=cfg['api_key'],
                    user_id=cfg['user_id'],
                )
                if await client.connect():
                    self._jellyfin = client
        return self._jellyfin

    def _build_embed(self, title: str, items: list[MediaItem]) -> discord.Embed:
        embed = discord.Embed(title=title, color=discord.Color.teal())
        for item in items[:15]:
            year = f' ({item.year})' if item.year else ''
            rating = f' ⭐ {item.rating:.1f}' if item.rating else ''
            summary = truncate(item.summary, 120) if item.summary else 'No description.'
            embed.add_field(
                name=f'{item.title}{year}{rating}',
                value=summary,
                inline=False,
            )
        if len(items) > 15:
            embed.set_footer(text=f'Showing 15 of {len(items)}')
        return embed

    @commands.hybrid_command(name='jf_movies', description='List or search movies in Jellyfin')
    @app_commands.describe(query='Title to search (leave blank for full list)')
    @require_auth()
    async def jf_movies(self, ctx: commands.Context, *, query: str = ''):
        jellyfin = await self._build_jellyfin()
        if not jellyfin:
            await ctx.send(
                'Jellyfin is not configured or unavailable. Set `jellyfin.api_key` and `jellyfin.user_id` in config.yaml.',
                ephemeral=True,
            )
            return
        await ctx.defer(ephemeral=True)
        try:
            items = await jellyfin.get_movies(query)
        except Exception as exc:
            await ctx.send(f'Jellyfin error: {exc}', ephemeral=True)
            return
        if not items:
            await ctx.send('No movies found.', ephemeral=True)
            return
        label = f'Movies matching "{query}"' if query else 'Movies'
        await ctx.send(embed=self._build_embed(f'{label} ({len(items)})', items), ephemeral=True)

    @commands.hybrid_command(name='jf_shows', description='List or search TV shows in Jellyfin')
    @app_commands.describe(query='Title to search (leave blank for full list)')
    @require_auth()
    async def jf_shows(self, ctx: commands.Context, *, query: str = ''):
        jellyfin = await self._build_jellyfin()
        if not jellyfin:
            await ctx.send(
                'Jellyfin is not configured or unavailable. Set `jellyfin.api_key` and `jellyfin.user_id` in config.yaml.',
                ephemeral=True,
            )
            return
        await ctx.defer(ephemeral=True)
        try:
            items = await jellyfin.get_shows(query)
        except Exception as exc:
            await ctx.send(f'Jellyfin error: {exc}', ephemeral=True)
            return
        if not items:
            await ctx.send('No shows found.', ephemeral=True)
            return
        label = f'Shows matching "{query}"' if query else 'TV Shows'
        await ctx.send(embed=self._build_embed(f'{label} ({len(items)})', items), ephemeral=True)

    @commands.hybrid_command(name='jf_recent', description='Show recently added media in Jellyfin')
    @require_auth()
    async def jf_recent(self, ctx: commands.Context):
        jellyfin = await self._build_jellyfin()
        if not jellyfin:
            await ctx.send('Jellyfin is not configured or unavailable.', ephemeral=True)
            return
        await ctx.defer(ephemeral=True)
        try:
            items = await jellyfin.recently_added(count=10)
        except Exception as exc:
            await ctx.send(f'Jellyfin error: {exc}', ephemeral=True)
            return
        if not items:
            await ctx.send('Nothing recently added.', ephemeral=True)
            return
        await ctx.send(embed=self._build_embed('Recently Added', items), ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(Jellyfin(bot))
