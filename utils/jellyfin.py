import logging
from dataclasses import dataclass
from typing import Optional

import aiohttp

log = logging.getLogger('mediabot.jellyfin')


@dataclass
class MediaItem:
    title: str
    year: Optional[int]
    rating: Optional[float]
    summary: str
    media_type: str  # 'movie' or 'show'


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
            'Fields': 'Overview,ProductionYear,CommunityRating',
        }
        if query:
            params['SearchTerm'] = query
        data = await self._get('/Items', params=params)
        return [self._map(i) for i in data.get('Items', [])]

    async def recently_added(self, count: int = 10) -> list[MediaItem]:
        params = {
            'IncludeItemTypes': 'Movie,Series',
            'Limit': count,
            'Fields': 'Overview,ProductionYear,CommunityRating',
        }
        data = await self._get(f'/Users/{self.user_id}/Items/Latest', params=params)
        return [self._map(i) for i in data]

    def _map(self, i: dict) -> MediaItem:
        rating = i.get('CommunityRating')
        return MediaItem(
            title=i.get('Name', 'Unknown'),
            year=i.get('ProductionYear'),
            rating=float(rating) if rating is not None else None,
            summary=(i.get('Overview') or '').strip(),
            media_type='movie' if i.get('Type') == 'Movie' else 'show',
        )
