from typing import Optional

import discord
from discord import app_commands
from discord.ext import commands

from utils.auth import require_auth
from utils.helpers import truncate
from utils.plex_client import MediaItem, PlexClient


class Library(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self._plex: Optional[PlexClient] = None

    async def _build_plex(self) -> Optional[PlexClient]:
        if self._plex is None:
            cfg = self.bot.config.get('plex', {})
            if cfg.get('token'):
                client = PlexClient(
                    host=cfg.get('host', 'http://localhost'),
                    port=int(cfg.get('port', 32400)),
                    token=cfg['token'],
                    movies_section=cfg.get('movies_section', 'Movies'),
                    shows_section=cfg.get('shows_section', 'TV Shows'),
                )
                if await client.connect():
                    self._plex = client
        return self._plex

    def _build_embed(self, title: str, items: list[MediaItem]) -> discord.Embed:
        embed = discord.Embed(title=title, color=discord.Color.purple())
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

    @commands.hybrid_command(name='movies', description='List or search movies in Plex')
    @app_commands.describe(query='Title to search (leave blank for full list)')
    @require_auth()
    async def movies(self, ctx: commands.Context, *, query: str = ''):
        plex = await self._build_plex()
        if not plex:
            await ctx.send('Plex is not configured or unavailable. Set `plex.token` in config.yaml.')
            return
        await ctx.defer()
        try:
            items = await plex.get_movies(query)
        except Exception as exc:
            await ctx.send(f'Plex error: {exc}')
            return
        if not items:
            await ctx.send('No movies found.')
            return
        label = f'Movies matching "{query}"' if query else 'Movies'
        await ctx.send(embed=self._build_embed(f'{label} ({len(items)})', items))

    @commands.hybrid_command(name='shows', description='List or search TV shows in Plex')
    @app_commands.describe(query='Title to search (leave blank for full list)')
    @require_auth()
    async def shows(self, ctx: commands.Context, *, query: str = ''):
        plex = await self._build_plex()
        if not plex:
            await ctx.send('Plex is not configured or unavailable. Set `plex.token` in config.yaml.')
            return
        await ctx.defer()
        try:
            items = await plex.get_shows(query)
        except Exception as exc:
            await ctx.send(f'Plex error: {exc}')
            return
        if not items:
            await ctx.send('No shows found.')
            return
        label = f'Shows matching "{query}"' if query else 'TV Shows'
        await ctx.send(embed=self._build_embed(f'{label} ({len(items)})', items))

    @commands.hybrid_command(name='recent', description='Show recently added media in Plex')
    @require_auth()
    async def recent(self, ctx: commands.Context):
        plex = await self._build_plex()
        if not plex:
            await ctx.send('Plex is not configured or unavailable.')
            return
        await ctx.defer()
        try:
            items = await plex.recently_added(count=10)
        except Exception as exc:
            await ctx.send(f'Plex error: {exc}')
            return
        if not items:
            await ctx.send('Nothing recently added.')
            return
        await ctx.send(embed=self._build_embed('Recently Added', items))


async def setup(bot: commands.Bot):
    await bot.add_cog(Library(bot))
