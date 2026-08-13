import asyncio
import logging
from dataclasses import dataclass
from typing import Optional

log = logging.getLogger('mediabot.plex')


@dataclass
class MediaItem:
    title: str
    year: Optional[int]
    rating: Optional[float]
    summary: str
    media_type: str


class PlexClient:
    def __init__(self, host: str, port: int, token: str,
                 movies_section: str = 'Movies', shows_section: str = 'TV Shows'):
        self._url = f'{host}:{port}'
        self._token = token
        self._movies_section = movies_section
        self._shows_section = shows_section
        self._server = None

    async def connect(self) -> bool:
        try:
            from plexapi.server import PlexServer
            self._server = await asyncio.to_thread(PlexServer, self._url, self._token)
            log.info('Connected to Plex')
            return True
        except Exception as exc:
            log.warning(f'Plex connection failed: {exc}')
            return False

    async def get_movies(self, query: str = '') -> list[MediaItem]:
        section = await asyncio.to_thread(
            self._server.library.section, self._movies_section
        )
        items = await asyncio.to_thread(section.search, title=query) if query \
            else await asyncio.to_thread(section.all)
        return [self._map(i) for i in items]

    async def get_shows(self, query: str = '') -> list[MediaItem]:
        section = await asyncio.to_thread(
            self._server.library.section, self._shows_section
        )
        items = await asyncio.to_thread(section.search, title=query) if query \
            else await asyncio.to_thread(section.all)
        return [self._map(i) for i in items]

    async def recently_added(self, count: int = 10) -> list[MediaItem]:
        items = await asyncio.to_thread(self._server.library.recentlyAdded)
        return [self._map(i) for i in items[:count]]

    def _map(self, item) -> MediaItem:
        return MediaItem(
            title=item.title,
            year=getattr(item, 'year', None),
            rating=getattr(item, 'rating', None),
            summary=(getattr(item, 'summary', '') or '').strip(),
            media_type=item.type,
        )
