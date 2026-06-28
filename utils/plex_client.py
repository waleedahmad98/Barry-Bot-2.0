import asyncio
import logging
import shutil
from dataclasses import dataclass
from pathlib import Path
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

    async def search_raw(self, title: str, media_type: str) -> list:
        """Return raw plexapi objects matching title (needed for deletion)."""
        section_name = self._movies_section if media_type == 'movie' else self._shows_section
        section = await asyncio.to_thread(self._server.library.section, section_name)
        return await asyncio.to_thread(section.search, title=title)

    def item_disk_paths(self, item) -> list[str]:
        """Return the filesystem paths that belong to this item."""
        if item.type == 'show':
            # locations is a list of root show directories
            return list(item.locations)
        elif item.type == 'movie':
            # parts hold individual video files
            paths = []
            for media in item.media:
                for part in media.parts:
                    paths.append(part.file)
            return paths
        return []

    async def delete_item(self, item) -> list[str]:
        """Delete an item's files from disk and remove it from the Plex library.

        Returns the list of paths that were deleted.
        """
        paths = self.item_disk_paths(item)
        deleted: list[str] = []

        for path_str in paths:
            p = Path(path_str)
            if item.type == 'show':
                if p.is_dir():
                    await asyncio.to_thread(shutil.rmtree, p)
                    deleted.append(str(p))
                    log.info(f'Deleted show directory: {p}')
            elif item.type == 'movie':
                if p.is_file():
                    parent = p.parent
                    await asyncio.to_thread(p.unlink)
                    deleted.append(str(p))
                    log.info(f'Deleted movie file: {p}')
                    # Remove the movie's folder if it is now empty
                    try:
                        await asyncio.to_thread(parent.rmdir)
                        deleted.append(str(parent))
                        log.info(f'Removed empty folder: {parent}')
                    except OSError:
                        pass  # folder not empty (extras, subtitles, etc.)

        # Remove the item from the Plex database
        try:
            await asyncio.to_thread(item.delete)
        except Exception as exc:
            log.warning(f'Plex item.delete() failed ({exc}), triggering library refresh instead')
            section_name = self._movies_section if item.type == 'movie' else self._shows_section
            section = await asyncio.to_thread(self._server.library.section, section_name)
            await asyncio.to_thread(section.update)

        return deleted

    def _map(self, item) -> MediaItem:
        return MediaItem(
            title=item.title,
            year=getattr(item, 'year', None),
            rating=getattr(item, 'rating', None),
            summary=(getattr(item, 'summary', '') or '').strip(),
            media_type=item.type,
        )
