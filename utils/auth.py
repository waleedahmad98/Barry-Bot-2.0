import json
from pathlib import Path

import discord
from discord.ext import commands

_ALLOWLIST = Path('data/allowlist.json')


def _load() -> set[int]:
    if _ALLOWLIST.exists():
        return set(json.loads(_ALLOWLIST.read_text()))
    return set()


def _save(ids: set[int]):
    _ALLOWLIST.write_text(json.dumps(sorted(ids)))


def add_user(user_id: int):
    ids = _load()
    ids.add(user_id)
    _save(ids)


def remove_user(user_id: int) -> bool:
    ids = _load()
    if user_id not in ids:
        return False
    ids.discard(user_id)
    _save(ids)
    return True


def list_dynamic_users() -> set[int]:
    return _load()


def is_authorized(bot: commands.Bot, user: discord.User | discord.Member) -> bool:
    cfg = bot.config
    owner_id = cfg['discord'].get('owner_id')
    if owner_id and user.id == int(owner_id):
        return True
    static = {int(uid) for uid in cfg.get('allowed_users', [])}
    return user.id in static or user.id in _load()


def require_auth():
    async def predicate(ctx: commands.Context) -> bool:
        if is_authorized(ctx.bot, ctx.author):
            return True
        msg = 'You are not authorized to use this bot.'
        if ctx.interaction:
            await ctx.interaction.response.send_message(msg, ephemeral=True)
        else:
            await ctx.send(msg)
        return False
    return commands.check(predicate)
