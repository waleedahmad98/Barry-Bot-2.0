import discord
from discord import app_commands
from discord.ext import commands

from utils.auth import add_user, is_authorized, list_dynamic_users, remove_user


class Admin(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    def _is_owner(self, user: discord.User | discord.Member) -> bool:
        owner_id = self.bot.config['discord'].get('owner_id')
        return bool(owner_id and user.id == int(owner_id))

    def _owner_only(self):
        async def predicate(ctx: commands.Context) -> bool:
            if self._is_owner(ctx.author):
                return True
            msg = 'Only the bot owner can use this command.'
            if ctx.interaction:
                await ctx.interaction.response.send_message(msg, ephemeral=True)
            else:
                await ctx.send(msg)
            return False
        return commands.check(predicate)

    @commands.hybrid_command(name='allow', description='Allow a user to use the bot')
    @app_commands.describe(user='User to add to the allowlist')
    async def allow(self, ctx: commands.Context, user: discord.User):
        if not self._is_owner(ctx.author):
            await ctx.send('Only the owner can manage the allowlist.')
            return
        add_user(user.id)
        await ctx.send(f'Added {user.mention} to the allowlist.', allowed_mentions=discord.AllowedMentions.none())

    @commands.hybrid_command(name='deny', description='Remove a user from the allowlist')
    @app_commands.describe(user='User to remove')
    async def deny(self, ctx: commands.Context, user: discord.User):
        if not self._is_owner(ctx.author):
            await ctx.send('Only the owner can manage the allowlist.')
            return
        if remove_user(user.id):
            await ctx.send(f'Removed {user.mention} from the allowlist.', allowed_mentions=discord.AllowedMentions.none())
        else:
            await ctx.send(f'{user.mention} is not in the dynamic allowlist.', allowed_mentions=discord.AllowedMentions.none())

    @commands.hybrid_command(name='allowed', description='Show all users allowed to use the bot')
    async def allowed(self, ctx: commands.Context):
        if not is_authorized(self.bot, ctx.author):
            await ctx.send('Not authorized.')
            return

        cfg = self.bot.config
        owner_id = cfg['discord'].get('owner_id')
        static = {int(uid) for uid in cfg.get('allowed_users', [])}
        dynamic = list_dynamic_users()

        embed = discord.Embed(title='Allowed Users', color=discord.Color.green())
        if owner_id:
            embed.add_field(name='Owner', value=f'<@{owner_id}>', inline=False)
        if static:
            embed.add_field(name='Config (static)', value=' '.join(f'<@{u}>' for u in sorted(static)), inline=False)
        if dynamic:
            embed.add_field(name='Added via !allow', value=' '.join(f'<@{u}>' for u in sorted(dynamic)), inline=False)
        if not (owner_id or static or dynamic):
            embed.description = 'No users configured.'

        await ctx.send(embed=embed)

    @commands.hybrid_command(name='reload', description='Reload a bot cog')
    @app_commands.describe(cog='Cog name: torrents, library, rss, admin')
    async def reload(self, ctx: commands.Context, cog: str):
        if not self._is_owner(ctx.author):
            await ctx.send('Only the owner can reload cogs.')
            return
        try:
            await self.bot.reload_extension(f'cogs.{cog}')
            await ctx.send(f'Reloaded `cogs.{cog}`.')
        except Exception as exc:
            await ctx.send(f'Failed to reload: {exc}')

    @commands.hybrid_command(name='sync', description='Sync slash commands with Discord')
    async def sync(self, ctx: commands.Context):
        if not self._is_owner(ctx.author):
            await ctx.send('Only the owner can sync commands.')
            return
        synced = await self.bot.tree.sync()
        await ctx.send(f'Synced {len(synced)} slash command(s).')

    @commands.hybrid_command(name='ping', description='Check bot latency')
    async def ping(self, ctx: commands.Context):
        if not is_authorized(self.bot, ctx.author):
            return
        await ctx.send(f'Pong! `{self.bot.latency * 1000:.1f} ms`')

    @commands.hybrid_command(name='status', description='Show bot and service status')
    async def status(self, ctx: commands.Context):
        if not is_authorized(self.bot, ctx.author):
            return

        cfg = self.bot.config
        embed = discord.Embed(title='Bot Status', color=discord.Color.blue())

        qb_cfg = cfg.get('qbittorrent', {})
        embed.add_field(
            name='qBittorrent',
            value=f'`{qb_cfg.get("host", "?")}:{qb_cfg.get("port", "?")}`',
            inline=True,
        )

        plex_cfg = cfg.get('plex', {})
        plex_val = f'`{plex_cfg.get("host")}:{plex_cfg.get("port")}`' if plex_cfg.get('token') else 'Not configured'
        embed.add_field(name='Plex', value=plex_val, inline=True)

        idx_cfg = cfg.get('indexer', {})
        idx_val = (
            f'{idx_cfg.get("type", "").capitalize()} `{idx_cfg.get("host")}:{idx_cfg.get("port")}`'
            if idx_cfg.get('api_key')
            else 'Not configured'
        )
        embed.add_field(name='Indexer', value=idx_val, inline=True)

        from cogs.rss import _load_feeds
        rss_feeds = _load_feeds()
        embed.add_field(name='RSS feeds', value=str(len(rss_feeds)), inline=True)
        embed.add_field(name='Latency', value=f'{self.bot.latency * 1000:.1f} ms', inline=True)

        await ctx.send(embed=embed)


async def setup(bot: commands.Bot):
    await bot.add_cog(Admin(bot))
