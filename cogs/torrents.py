from typing import Optional

import discord
from discord import app_commands
from discord.ext import commands

from utils.auth import require_auth
from utils.helpers import format_size, format_state, progress_bar, truncate
from utils.jackett import CATEGORIES, JackettClient, TorrentResult
from utils.qbit import QBitClient


# ── Interactive views ──────────────────────────────────────────────────────────

class PathButton(discord.ui.Button):
    """A button that triggers a download to a specific save path."""

    def __init__(self, label: str, save_path: str):
        super().__init__(label=label.capitalize(), style=discord.ButtonStyle.primary)
        self.save_path = save_path

    async def callback(self, interaction: discord.Interaction):
        await self.view.start_download(interaction, self.save_path)


class DownloadPathView(discord.ui.View):
    def __init__(self, result: TorrentResult, paths: dict[str, str], qbit: QBitClient):
        super().__init__(timeout=60)
        self.result = result
        self.qbit = qbit
        for label, path in paths.items():
            self.add_item(PathButton(label, path))

    async def start_download(self, interaction: discord.Interaction, save_path: str):
        url = self.result.download_url
        if not url:
            await interaction.response.send_message('No download URL available.', ephemeral=True)
            return

        for child in self.children:
            child.disabled = True
        await interaction.response.edit_message(view=self)

        success = await self.qbit.add_torrent(url, save_path=save_path)
        color = discord.Color.green() if success else discord.Color.red()
        title = 'Download started' if success else 'Failed to add torrent'
        desc = f'**{truncate(self.result.title, 200)}**\nSaving to: `{save_path}`' if success else None
        await interaction.followup.send(embed=discord.Embed(title=title, description=desc, color=color))


class SearchResultsView(discord.ui.View):
    def __init__(self, results: list[TorrentResult], paths: dict[str, str], qbit: QBitClient):
        super().__init__(timeout=120)
        self.results = results
        self.paths = paths
        self.qbit = qbit

        options = [
            discord.SelectOption(
                label=truncate(r.title, 100),
                description=f'{format_size(r.size)} · {r.seeders} seeds · {r.indexer}',
                value=str(i),
            )
            for i, r in enumerate(results[:25])
        ]
        select = discord.ui.Select(placeholder='Select a result to download…', options=options)
        select.callback = self._on_select
        self.add_item(select)

    async def _on_select(self, interaction: discord.Interaction):
        idx = int(interaction.data['values'][0])
        result = self.results[idx]

        for child in self.children:
            child.disabled = True
        await interaction.response.edit_message(view=self)

        embed = discord.Embed(
            title='Where to save?',
            description=f'**{truncate(result.title, 200)}**\nSize: {format_size(result.size)}',
            color=discord.Color.blurple(),
        )
        await interaction.followup.send(
            embed=embed, view=DownloadPathView(result, self.paths, self.qbit)
        )


# ── Cog ───────────────────────────────────────────────────────────────────────

class Torrents(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self._jackett: Optional[JackettClient] = None
        self._qbit: Optional[QBitClient] = None

    def _build_jackett(self) -> Optional[JackettClient]:
        if self._jackett is None:
            cfg = self.bot.config.get('indexer', {})
            if cfg.get('api_key'):
                self._jackett = JackettClient(
                    host=cfg.get('host', 'http://localhost'),
                    port=int(cfg.get('port', 9117)),
                    api_key=cfg['api_key'],
                )
        return self._jackett

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

    def _download_paths(self) -> dict[str, str]:
        paths = self.bot.config.get('paths', {})
        return {k: v for k, v in paths.items()}

    # ── Commands ───────────────────────────────────────────────────────────────

    @commands.hybrid_command(name='search', description='Search torrents via Jackett/Prowlarr')
    @app_commands.describe(query='Search query', category='Filter: movies, shows, or all')
    @require_auth()
    async def search(self, ctx: commands.Context, query: str, category: str = 'all'):
        if category not in CATEGORIES:
            await ctx.send(f'Category must be one of: {", ".join(CATEGORIES)}')
            return

        jackett = self._build_jackett()
        if not jackett:
            await ctx.send(
                'Torrent search is not configured. Set `indexer.api_key` in config.yaml.\n'
                'You can still download directly with `!download <magnet/url>`.'
            )
            return

        qbit = await self._build_qbit()
        if not qbit:
            await ctx.send('qBittorrent is unavailable. Check config and that it is running.')
            return

        await ctx.defer()

        try:
            results = await jackett.search(query, category=category, limit=25)
        except Exception as exc:
            await ctx.send(f'Search failed: {exc}')
            return

        if not results:
            await ctx.send(f'No results for "{query}".')
            return

        embed = discord.Embed(
            title=f'Search: {query}',
            description=f'{len(results)} result(s) — pick one from the dropdown:',
            color=discord.Color.blurple(),
        )
        for r in results[:10]:
            embed.add_field(
                name=truncate(r.title, 50),
                value=f'{format_size(r.size)} · {r.seeders} seeds · {r.indexer}',
                inline=False,
            )
        if len(results) > 10:
            embed.set_footer(text=f'+{len(results) - 10} more in dropdown')

        view = SearchResultsView(results, self._download_paths(), qbit)
        await ctx.send(embed=embed, view=view)

    @commands.hybrid_command(
        name='download', description='Download a torrent by magnet link or URL'
    )
    @app_commands.describe(
        url='Magnet link or direct torrent URL',
        category='Save location: movies, shows, or downloads',
    )
    @require_auth()
    async def download(self, ctx: commands.Context, url: str, category: str = 'downloads'):
        qbit = await self._build_qbit()
        if not qbit:
            await ctx.send('qBittorrent is unavailable.')
            return

        save_path = self.bot.config.get('paths', {}).get(category)
        await ctx.defer()

        success = await qbit.add_torrent(url, save_path=save_path)
        color = discord.Color.green() if success else discord.Color.red()
        desc = f'Saving to: `{save_path or "qBittorrent default"}`' if success else None
        await ctx.send(
            embed=discord.Embed(
                title='Download started' if success else 'Failed to add torrent',
                description=desc,
                color=color,
            )
        )

    @commands.hybrid_command(name='downloads', description='List current downloads')
    @require_auth()
    async def downloads(self, ctx: commands.Context):
        qbit = await self._build_qbit()
        if not qbit:
            await ctx.send('qBittorrent is unavailable.')
            return

        await ctx.defer()
        torrents = await qbit.list_torrents()

        if not torrents:
            await ctx.send('No torrents in qBittorrent.')
            return

        active = [t for t in torrents if t.progress < 1.0]
        done = [t for t in torrents if t.progress >= 1.0]

        embed = discord.Embed(
            title=f'Downloads — {len(active)} active, {len(done)} done',
            color=discord.Color.blue(),
        )
        for t in active[:8]:
            embed.add_field(
                name=truncate(t.name, 50),
                value=f'`{progress_bar(t.progress)}`\n{format_state(t.state)} · {format_size(t.size)}',
                inline=False,
            )
        for t in done[:5]:
            embed.add_field(
                name=truncate(t.name, 50),
                value=f'Done · {format_size(t.size)} · {t.save_path}',
                inline=False,
            )
        if len(torrents) > 13:
            embed.set_footer(text=f'Showing 13 of {len(torrents)}')

        await ctx.send(embed=embed)

    @commands.hybrid_command(
        name='dl_remove', description='Remove a download (partial name match)'
    )
    @app_commands.describe(name='Partial torrent name', delete_files='Also delete downloaded files')
    @require_auth()
    async def dl_remove(
        self, ctx: commands.Context, name: str, delete_files: bool = False
    ):
        qbit = await self._build_qbit()
        if not qbit:
            await ctx.send('qBittorrent is unavailable.')
            return

        await ctx.defer()
        torrents = await qbit.list_torrents()
        matches = [t for t in torrents if name.lower() in t.name.lower()]

        if not matches:
            await ctx.send(f'No torrent matching "{name}".')
            return
        if len(matches) > 1:
            listing = '\n'.join(f'- {t.name}' for t in matches[:6])
            await ctx.send(f'Multiple matches — be more specific:\n{listing}')
            return

        t = matches[0]
        await qbit.remove(t.hash, delete_files=delete_files)
        suffix = ' (files deleted)' if delete_files else ''
        await ctx.send(f'Removed **{t.name}**{suffix}.')

    @commands.hybrid_command(name='dl_pause', description='Pause a download')
    @app_commands.describe(name='Partial torrent name')
    @require_auth()
    async def dl_pause(self, ctx: commands.Context, name: str):
        await self._toggle(ctx, name, pause=True)

    @commands.hybrid_command(name='dl_resume', description='Resume a paused download')
    @app_commands.describe(name='Partial torrent name')
    @require_auth()
    async def dl_resume(self, ctx: commands.Context, name: str):
        await self._toggle(ctx, name, pause=False)

    async def _toggle(self, ctx: commands.Context, name: str, pause: bool):
        qbit = await self._build_qbit()
        if not qbit:
            await ctx.send('qBittorrent is unavailable.')
            return
        await ctx.defer()
        torrents = await qbit.list_torrents()
        matches = [t for t in torrents if name.lower() in t.name.lower()]
        if not matches:
            await ctx.send(f'No torrent matching "{name}".')
            return
        if len(matches) > 1:
            listing = '\n'.join(f'- {t.name}' for t in matches[:6])
            await ctx.send(f'Multiple matches:\n{listing}')
            return
        t = matches[0]
        if pause:
            await qbit.pause(t.hash)
            await ctx.send(f'Paused **{t.name}**.')
        else:
            await qbit.resume(t.hash)
            await ctx.send(f'Resumed **{t.name}**.')


async def setup(bot: commands.Bot):
    await bot.add_cog(Torrents(bot))
