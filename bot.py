import asyncio
import logging
from pathlib import Path

import discord
import yaml
from discord.ext import commands

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S',
)
log = logging.getLogger('mediabot')


def load_config(path: str = 'config.yaml') -> dict:
    with open(path) as f:
        return yaml.safe_load(f)


class MediaBot(commands.Bot):
    def __init__(self, config: dict):
        intents = discord.Intents.default()
        intents.message_content = True
        super().__init__(
            command_prefix=config['discord'].get('prefix', '!'),
            intents=intents,
        )
        self.config = config

    async def setup_hook(self):
        for cog in ('cogs.torrents', 'cogs.library', 'cogs.rss', 'cogs.admin'):
            try:
                await self.load_extension(cog)
                log.info(f'Loaded {cog}')
            except Exception as exc:
                log.error(f'Failed to load {cog}: {exc}')

    async def on_ready(self):
        log.info(f'Logged in as {self.user} (id={self.user.id})')
        await self.change_presence(
            activity=discord.Activity(type=discord.ActivityType.watching, name='your commands')
        )

    async def on_command_error(self, ctx: commands.Context, error):
        if isinstance(error, (commands.CheckFailure, commands.CommandNotFound)):
            return
        if isinstance(error, commands.MissingRequiredArgument):
            await ctx.send(f'Missing argument: `{error.param.name}`')
            return
        if isinstance(error, commands.CommandInvokeError):
            inner = error.original
            if isinstance(inner, discord.Forbidden):
                log.error(
                    f'Missing permissions in #{ctx.channel} '
                    f'(guild={ctx.guild}): {inner}'
                )
                # Try a plain-text reply; if that also fails, just log it
                try:
                    await ctx.send(
                        'Missing permissions. Make sure the bot has '
                        '**Send Messages** and **Embed Links** in this channel.'
                    )
                except discord.Forbidden:
                    pass
                return
        log.error(f'Error in {ctx.command}: {error}', exc_info=error)
        try:
            await ctx.send(f'Error: {error}')
        except discord.Forbidden:
            log.error(f'Also cannot send error message to #{ctx.channel}')


async def main():
    config = load_config()
    Path('data').mkdir(exist_ok=True)
    bot = MediaBot(config)
    async with bot:
        await bot.start(config['discord']['token'])


if __name__ == '__main__':
    asyncio.run(main())
