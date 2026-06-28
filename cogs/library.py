from typing import Optional

import discord
from discord import app_commands
from discord.ext import commands

from utils.auth import require_auth
from utils.helpers import truncate
from utils.plex_client import MediaItem, PlexClient


class ConfirmDeleteView(discord.ui.View):
    def __init__(self, plex: PlexClient, item, paths: list[str]):
        super().__init__(timeout=30)
        self.plex = plex
        self.item = item
        self.paths = paths

    async def _disable(self, interaction: discord.Interaction):
        for child in self.children:
            child.disabled = True
        await interaction.response.edit_message(view=self)

    @discord.ui.button(label='Yes, delete', style=discord.ButtonStyle.danger)
    async def confirm(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._disable(interaction)
        try:
            deleted = await self.plex.delete_item(self.item)
        except Exception as exc:
            await interaction.followup.send(f'Deletion failed: {exc}')
            return

        if deleted:
            body = '\n'.join(f'`{p}`' for p in deleted)
            embed = discord.Embed(
                title=f'Deleted: {self.item.title}',
                description=body,
                color=discord.Color.green(),
            )
        else:
            embed = discord.Embed(
                title=f'Removed from Plex: {self.item.title}',
                description='No files were found on disk (already deleted?).',
                color=discord.Color.orange(),
            )
        await interaction.followup.send(embed=embed)

    @discord.ui.button(label='Cancel', style=discord.ButtonStyle.secondary)
    async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._disable(interaction)
        await interaction.followup.send('Cancelled.', ephemeral=True)


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

    @commands.hybrid_command(name='delete', description='Delete a movie or show from Plex and disk')
    @app_commands.describe(
        title='Title to delete',
        media_type='movies or shows',
    )
    @require_auth()
    async def delete(self, ctx: commands.Context, title: str, media_type: str = 'shows'):
        if media_type not in ('movies', 'shows'):
            await ctx.send('`media_type` must be `movies` or `shows`.')
            return

        plex = await self._build_plex()
        if not plex:
            await ctx.send('Plex is not configured or unavailable.')
            return

        await ctx.defer()
        plex_type = 'movie' if media_type == 'movies' else 'show'
        try:
            results = await plex.search_raw(title, plex_type)
        except Exception as exc:
            await ctx.send(f'Plex error: {exc}')
            return

        if not results:
            await ctx.send(f'Nothing found for "{title}" in {media_type}.')
            return

        if len(results) > 1:
            listing = '\n'.join(
                f'- {r.title} ({getattr(r, "year", "?")})' for r in results[:8]
            )
            await ctx.send(
                f'Multiple matches — be more specific:\n{listing}'
            )
            return

        item = results[0]
        paths = plex.item_disk_paths(item)
        year = f' ({item.year})' if getattr(item, 'year', None) else ''

        embed = discord.Embed(
            title=f'Delete {item.title}{year}?',
            description='This will permanently remove the files from disk and from Plex.',
            color=discord.Color.red(),
        )
        if paths:
            embed.add_field(
                name='Paths that will be deleted',
                value='\n'.join(f'`{p}`' for p in paths),
                inline=False,
            )
        else:
            embed.add_field(name='Warning', value='No file paths found — Plex entry will still be removed.', inline=False)

        await ctx.send(embed=embed, view=ConfirmDeleteView(plex, item, paths))

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
