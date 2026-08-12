from typing import Awaitable, Callable, Optional

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


def _series_season_numbers(result: SeriesResult) -> list[int]:
    return sorted(
        {s.get('seasonNumber') for s in result.raw.get('seasons', []) if s.get('seasonNumber') is not None}
    )


def _season_label(n: int) -> str:
    return 'Specials' if n == 0 else f'Season {n}'


async def _complete_series_request(
    interaction: discord.Interaction,
    sonarr: SonarrClient,
    result: SeriesResult,
    seasons: Optional[list[int]],
    season_note: Optional[str],
):
    success, reason = await sonarr.add(result, seasons=seasons)

    if success:
        if interaction.channel is not None:
            embed = _request_card(
                interaction.user, result.title, result.year, result.overview, result.poster_url
            )
            if season_note:
                embed.add_field(name='Monitoring', value=season_note, inline=False)
            await interaction.channel.send(embed=embed)
    else:
        desc = f'**{truncate(result.title, 200)}**'
        if reason:
            desc += f'\n_{reason}_'
        await interaction.followup.send(
            embed=discord.Embed(title='Could not request', description=desc, color=discord.Color.red()),
            ephemeral=True,
        )


class SeasonSelectView(discord.ui.View):
    def __init__(self, result: SeriesResult, sonarr: SonarrClient):
        super().__init__(timeout=120)
        self.result = result
        self.sonarr = sonarr

        options = [discord.SelectOption(label='All seasons', value='all', default=True)]
        options += [
            discord.SelectOption(label=_season_label(n), value=str(n))
            for n in _series_season_numbers(result)[:24]  # Discord caps a select at 25 options total
        ]
        select = discord.ui.Select(
            placeholder='Select season(s) to monitor…',
            min_values=1,
            max_values=len(options),
            options=options,
        )
        select.callback = self._on_select
        self.add_item(select)

    async def _on_select(self, interaction: discord.Interaction):
        values = interaction.data['values']

        for child in self.children:
            child.disabled = True
        await interaction.response.edit_message(view=self)

        if 'all' in values:
            seasons, season_note = None, None
        else:
            numbers = sorted(int(v) for v in values)
            seasons = numbers
            season_note = ', '.join(_season_label(n) for n in numbers)

        await _complete_series_request(interaction, self.sonarr, self.result, seasons, season_note)


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

        # Already-added or single-season shows have nothing to choose between —
        # skip straight to adding rather than showing a pointless season picker.
        if result.already_added or len(_series_season_numbers(result)) <= 1:
            await _complete_series_request(interaction, self.sonarr, result, seasons=None, season_note=None)
            return

        embed = discord.Embed(
            title=f'Which seasons of {truncate(result.title, 200)}?',
            description='Pick one or more, or leave "All seasons" selected.',
            color=discord.Color.gold(),
        )
        await interaction.followup.send(embed=embed, view=SeasonSelectView(result, self.sonarr), ephemeral=True)


class ConfirmRemoveView(discord.ui.View):
    def __init__(self, remove: Callable[[], Awaitable[tuple[bool, Optional[str]]]], title: str):
        super().__init__(timeout=30)
        self._remove = remove
        self._title = title

    async def _disable(self, interaction: discord.Interaction):
        for child in self.children:
            child.disabled = True
        await interaction.response.edit_message(view=self)

    @discord.ui.button(label='Yes, remove', style=discord.ButtonStyle.danger)
    async def confirm(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._disable(interaction)
        success, reason = await self._remove()
        color = discord.Color.green() if success else discord.Color.red()
        title = 'Removed' if success else 'Could not remove'
        desc = f'**{truncate(self._title, 200)}**'
        if reason:
            desc += f'\n_{reason}_'
        await interaction.followup.send(
            embed=discord.Embed(title=title, description=desc, color=color), ephemeral=True
        )

    @discord.ui.button(label='Cancel', style=discord.ButtonStyle.secondary)
    async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._disable(interaction)
        await interaction.followup.send('Cancelled.', ephemeral=True)


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

    @commands.hybrid_command(name='remove_movie', description='Remove a movie from Radarr')
    @app_commands.describe(
        title='Movie title (partial match ok)',
        delete_files='Also delete the downloaded files from disk',
    )
    @require_auth()
    async def remove_movie(self, ctx: commands.Context, title: str, delete_files: bool = True):
        radarr = await self._build_radarr()
        if not radarr:
            await ctx.send(
                'Radarr is not configured or unavailable. Set `radarr.api_key` in config.yaml.',
                ephemeral=True,
            )
            return

        await ctx.defer(ephemeral=True)

        try:
            library = await radarr.list_library()
        except Exception as exc:
            await ctx.send(f'Radarr lookup failed: {exc}', ephemeral=True)
            return

        matches = [m for m in library if title.lower() in m.title.lower()]
        if not matches:
            await ctx.send(f'No movie matching "{title}" in Radarr.', ephemeral=True)
            return
        if len(matches) > 1:
            listing = '\n'.join(f'- {m.title} ({m.year or "?"})' for m in matches[:8])
            await ctx.send(f'Multiple matches — be more specific:\n{listing}', ephemeral=True)
            return

        movie = matches[0]
        year = f' ({movie.year})' if movie.year else ''
        embed = discord.Embed(
            title=f'Remove {movie.title}{year} from Radarr?',
            description=(
                'This removes it from Radarr **and deletes its files from disk.**'
                if delete_files
                else 'This removes it from Radarr but leaves any downloaded files on disk.'
            ),
            color=discord.Color.red(),
        )
        await ctx.send(
            embed=embed,
            view=ConfirmRemoveView(lambda: radarr.remove(movie.id, delete_files), movie.title),
            ephemeral=True,
        )

    @commands.hybrid_command(name='remove_show', description='Remove a TV show from Sonarr')
    @app_commands.describe(
        title='Show title (partial match ok)',
        delete_files='Also delete the downloaded files from disk',
    )
    @require_auth()
    async def remove_show(self, ctx: commands.Context, title: str, delete_files: bool = True):
        sonarr = await self._build_sonarr()
        if not sonarr:
            await ctx.send(
                'Sonarr is not configured or unavailable. Set `sonarr.api_key` in config.yaml.',
                ephemeral=True,
            )
            return

        await ctx.defer(ephemeral=True)

        try:
            library = await sonarr.list_library()
        except Exception as exc:
            await ctx.send(f'Sonarr lookup failed: {exc}', ephemeral=True)
            return

        matches = [s for s in library if title.lower() in s.title.lower()]
        if not matches:
            await ctx.send(f'No show matching "{title}" in Sonarr.', ephemeral=True)
            return
        if len(matches) > 1:
            listing = '\n'.join(f'- {s.title} ({s.year or "?"})' for s in matches[:8])
            await ctx.send(f'Multiple matches — be more specific:\n{listing}', ephemeral=True)
            return

        series = matches[0]
        year = f' ({series.year})' if series.year else ''
        embed = discord.Embed(
            title=f'Remove {series.title}{year} from Sonarr?',
            description=(
                'This removes it from Sonarr **and deletes its files from disk.**'
                if delete_files
                else 'This removes it from Sonarr but leaves any downloaded files on disk.'
            ),
            color=discord.Color.red(),
        )
        await ctx.send(
            embed=embed,
            view=ConfirmRemoveView(lambda: sonarr.remove(series.id, delete_files), series.title),
            ephemeral=True,
        )


async def setup(bot: commands.Bot):
    await bot.add_cog(Requests(bot))
