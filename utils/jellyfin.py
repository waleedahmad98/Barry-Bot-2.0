import asyncio
import logging
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import aiohttp

log = logging.getLogger('mediabot.jellyfin')


@dataclass
class MediaItem:
    id: str
    title: str
    year: Optional[int]
    rating: Optional[float]
    summary: str
    media_type: str  # 'movie' or 'show'
    path: Optional[str]


class JellyfinClient:
    def __init__(self, host: str, port: int, api_key: str, user_id: str):
        self.base_url = f'{host}:{port}'
        self.api_key = api_key
        self.user_id = user_id

    def _headers(self) -> dict:
        return {'X-Emby-Token': self.api_key}

    async def _get(self, path: str, params: Optional[dict] = None):
        timeout = aiohttp.ClientTimeout(total=20)
        async with aiohttp.ClientSession(timeout=timeout, headers=self._headers()) as session:
            async with session.get(f'{self.base_url}{path}', params=params) as resp:
                resp.raise_for_status()
                return await resp.json()

    async def _delete(self, path: str):
        timeout = aiohttp.ClientTimeout(total=20)
        async with aiohttp.ClientSession(timeout=timeout, headers=self._headers()) as session:
            async with session.delete(f'{self.base_url}{path}') as resp:
                resp.raise_for_status()

    async def connect(self) -> bool:
        try:
            await self._get('/System/Info')
            log.info('Connected to Jellyfin')
            return True
        except Exception as exc:
            log.warning(f'Jellyfin connection failed: {exc}')
            return False

    async def get_movies(self, query: str = '') -> list[MediaItem]:
        return await self._items('Movie', query)

    async def get_shows(self, query: str = '') -> list[MediaItem]:
        return await self._items('Series', query)

    async def _items(self, item_type: str, query: str) -> list[MediaItem]:
        params = {
            'IncludeItemTypes': item_type,
            'Recursive': 'true',
            'userId': self.user_id,
            'Fields': 'Overview,Path,ProductionYear,CommunityRating',
        }
        if query:
            params['SearchTerm'] = query
        data = await self._get('/Items', params=params)
        return [self._map(i) for i in data.get('Items', [])]

    async def recently_added(self, count: int = 10) -> list[MediaItem]:
        params = {
            'IncludeItemTypes': 'Movie,Series',
            'Limit': count,
            'Fields': 'Overview,Path,ProductionYear,CommunityRating',
        }
        data = await self._get(f'/Users/{self.user_id}/Items/Latest', params=params)
        return [self._map(i) for i in data]

    async def search_raw(self, title: str, media_type: str) -> list[MediaItem]:
        """Return mapped items matching title (kept as its own method to mirror PlexClient)."""
        item_type = 'Movie' if media_type == 'movie' else 'Series'
        return await self._items(item_type, title)

    def item_disk_paths(self, item: MediaItem) -> list[str]:
        return [item.path] if item.path else []

    async def delete_item(self, item: MediaItem) -> list[str]:
        """Delete an item's files from disk and remove it from the Jellyfin library.

        Returns the list of paths that were deleted.
        """
        deleted: list[str] = []

        for path_str in self.item_disk_paths(item):
            p = Path(path_str)
            try:
                if item.media_type == 'show' and p.is_dir():
                    await asyncio.to_thread(shutil.rmtree, p)
                    deleted.append(str(p))
                    log.info(f'Deleted show directory: {p}')
                elif item.media_type == 'movie' and p.is_file():
                    parent = p.parent
                    await asyncio.to_thread(p.unlink)
                    deleted.append(str(p))
                    log.info(f'Deleted movie file: {p}')
                    try:
                        await asyncio.to_thread(parent.rmdir)
                        deleted.append(str(parent))
                        log.info(f'Removed empty folder: {parent}')
                    except OSError:
                        pass  # folder not empty (extras, subtitles, etc.)
            except OSError as exc:
                log.warning(f'Failed to delete {p}: {exc}')

        try:
            await self._delete(f'/Items/{item.id}')
        except Exception as exc:
            log.warning(f'Jellyfin item removal failed ({exc}); a library scan will catch up')

        return deleted

    def _map(self, i: dict) -> MediaItem:
        rating = i.get('CommunityRating')
        return MediaItem(
            id=i.get('Id', ''),
            title=i.get('Name', 'Unknown'),
            year=i.get('ProductionYear'),
            rating=float(rating) if rating is not None else None,
            summary=(i.get('Overview') or '').strip(),
            media_type='movie' if i.get('Type') == 'Movie' else 'show',
            path=i.get('Path'),
        )
