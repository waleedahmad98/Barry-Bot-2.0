from typing import Optional

import discord
from discord import app_commands
from discord.ext import commands

from utils.auth import require_auth
from utils.helpers import truncate
from utils.radarr import MovieResult, RadarrClient
from utils.sonarr import SeriesResult, SonarrClient


# ── Interactive views ──────────────────────────────────────────────────────────

def _field_desc(overview: str, already_added: bool, added_note: str) -> str:
    desc = truncate(overview, 100) if overview else 'No description.'
    if already_added:
        desc += f'\n_{added_note}_'
    return desc


def _request_card(
    user: discord.abc.User, title: str, year: Optional[int], overview: str, poster_url: Optional[str]
) -> discord.Embed:
    """A single-message 'requested by X' card — no service-specific wording, just who and what."""
    embed = discord.Embed(
        title=truncate(f'{title} ({year})' if year else title, 256),
        description=truncate(overview, 300) if overview else None,
        color=discord.Color.gold(),
    )
    embed.set_author(name=f'Requested by {user.display_name}', icon_url=user.display_avatar.url)
    if poster_url:
        embed.set_thumbnail(url=poster_url)
    return embed


class MovieRequestView(discord.ui.View):
    def __init__(self, results: list[MovieResult], radarr: RadarrClient):
        super().__init__(timeout=120)
        self.results = results
        self.radarr = radarr

        options = [
            discord.SelectOption(
                label=truncate(f'{r.title} ({r.year})' if r.year else r.title, 100),
                description=('Already in Radarr' if r.already_added else truncate(r.overview, 100)) or 'No description.',
                value=str(i),
            )
            for i, r in enumerate(results[:25])
        ]
        select = discord.ui.Select(placeholder='Select a movie to request…', options=options)
        select.callback = self._on_select
        self.add_item(select)

    async def _on_select(self, interaction: discord.Interaction):
        idx = int(interaction.data['values'][0])
        result = self.results[idx]

        for child in self.children:
            child.disabled = True
        await interaction.response.edit_message(view=self)

        success, reason = await self.radarr.add(result)

        if success:
            if interaction.channel is not None:
                await interaction.channel.send(
                    embed=_request_card(
                        interaction.user, result.title, result.year, result.overview, result.poster_url
                    )
                )
        else:
            desc = f'**{truncate(result.title, 200)}**'
            if reason:
                desc += f'\n_{reason}_'
            await interaction.followup.send(
                embed=discord.Embed(title='Could not request', description=desc, color=discord.Color.red()),
                ephemeral=True,
            )


class SeriesRequestView(discord.ui.View):
    def __init__(self, results: list[SeriesResult], sonarr: SonarrClient):
        super().__init__(timeout=120)
        self.results = results
        self.sonarr = sonarr

        options = [
            discord.SelectOption(
                label=truncate(f'{r.title} ({r.year})' if r.year else r.title, 100),
                description=('Already in Sonarr' if r.already_added else truncate(r.overview, 100)) or 'No description.',
                value=str(i),
            )
            for i, r in enumerate(results[:25])
        ]
        select = discord.ui.Select(placeholder='Select a show to request…', options=options)
        select.callback = self._on_select
        self.add_item(select)

    async def _on_select(self, interaction: discord.Interaction):
        idx = int(interaction.data['values'][0])
        result = self.results[idx]

        for child in self.children:
            child.disabled = True
        await interaction.response.edit_message(view=self)

        success, reason = await self.sonarr.add(result)

        if success:
            if interaction.channel is not None:
                await interaction.channel.send(
                    embed=_request_card(
                        interaction.user, result.title, result.year, result.overview, result.poster_url
                    )
                )
        else:
            desc = f'**{truncate(result.title, 200)}**'
            if reason:
                desc += f'\n_{reason}_'
            await interaction.followup.send(
                embed=discord.Embed(title='Could not request', description=desc, color=discord.Color.red()),
                ephemeral=True,
            )


# ── Cog ───────────────────────────────────────────────────────────────────────

class Requests(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self._radarr: Optional[RadarrClient] = None
        self._sonarr: Optional[SonarrClient] = None

    async def _build_radarr(self) -> Optional[RadarrClient]:
        if self._radarr is None:
            cfg = self.bot.config.get('radarr', {})
            if cfg.get('api_key'):
                client = RadarrClient(
                    host=cfg.get('host', 'http://localhost'),
                    port=int(cfg.get('port', 7878)),
                    api_key=cfg['api_key'],
                    quality_profile=cfg.get('quality_profile', 'HD-1080p'),
                    root_folder=cfg.get('root_folder', '/movies'),
                )
                if await client.connect():
                    self._radarr = client
        return self._radarr

    async def _build_sonarr(self) -> Optional[SonarrClient]:
        if self._sonarr is None:
            cfg = self.bot.config.get('sonarr', {})
            if cfg.get('api_key'):
                client = SonarrClient(
                    host=cfg.get('host', 'http://localhost'),
                    port=int(cfg.get('port', 8989)),
                    api_key=cfg['api_key'],
                    quality_profile=cfg.get('quality_profile', 'HD-1080p'),
                    root_folder=cfg.get('root_folder', '/tv'),
                )
                if await client.connect():
                    self._sonarr = client
        return self._sonarr

    # ── Commands ───────────────────────────────────────────────────────────────

    @commands.hybrid_command(name='request_movie', description='Request a movie via Radarr')
    @app_commands.describe(query='Movie title to search for')
    @require_auth()
    async def request_movie(self, ctx: commands.Context, *, query: str):
        radarr = await self._build_radarr()
        if not radarr:
            await ctx.send(
                'Radarr is not configured or unavailable. Set `radarr.api_key` in config.yaml.',
                ephemeral=True,
            )
            return

        await ctx.defer(ephemeral=True)

        try:
            results = await radarr.lookup(query)
        except Exception as exc:
            await ctx.send(f'Radarr lookup failed: {exc}', ephemeral=True)
            return

        if not results:
            await ctx.send(f'No movies found for "{query}".', ephemeral=True)
            return

        embed = discord.Embed(
            title=f'Request a movie: {query}',
            description=f'{len(results)} result(s) — pick one from the dropdown:',
            color=discord.Color.gold(),
        )
        for r in results[:10]:
            year = f' ({r.year})' if r.year else ''
            embed.add_field(
                name=truncate(f'{r.title}{year}', 100),
                value=_field_desc(r.overview, r.already_added, 'Already in Radarr'),
                inline=False,
            )
        if len(results) > 10:
            embed.set_footer(text=f'+{len(results) - 10} more in dropdown')

        await ctx.send(embed=embed, view=MovieRequestView(results, radarr), ephemeral=True)

    @commands.hybrid_command(name='request_show', description='Request a TV show via Sonarr')
    @app_commands.describe(query='Show title to search for')
    @require_auth()
    async def request_show(self, ctx: commands.Context, *, query: str):
        sonarr = await self._build_sonarr()
        if not sonarr:
            await ctx.send(
                'Sonarr is not configured or unavailable. Set `sonarr.api_key` in config.yaml.',
                ephemeral=True,
            )
            return

        await ctx.defer(ephemeral=True)

        try:
            results = await sonarr.lookup(query)
        except Exception as exc:
            await ctx.send(f'Sonarr lookup failed: {exc}', ephemeral=True)
            return

        if not results:
            await ctx.send(f'No shows found for "{query}".', ephemeral=True)
            return

        embed = discord.Embed(
            title=f'Request a show: {query}',
            description=f'{len(results)} result(s) — pick one from the dropdown:',
            color=discord.Color.gold(),
        )
        for r in results[:10]:
            year = f' ({r.year})' if r.year else ''
            embed.add_field(
                name=truncate(f'{r.title}{year}', 100),
                value=_field_desc(r.overview, r.already_added, 'Already in Sonarr'),
                inline=False,
            )
        if len(results) > 10:
            embed.set_footer(text=f'+{len(results) - 10} more in dropdown')

        await ctx.send(embed=embed, view=SeriesRequestView(results, sonarr), ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(Requests(bot))
