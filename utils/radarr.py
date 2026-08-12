import logging
from dataclasses import dataclass, field
from typing import Optional

from utils.arr import ArrClient

log = logging.getLogger('mediabot.radarr')


@dataclass
class MovieResult:
    id: int
    tmdb_id: int
    title: str
    year: Optional[int]
    overview: str
    poster_url: Optional[str]
    already_added: bool
    raw: dict = field(repr=False)


class RadarrClient(ArrClient):
    async def lookup(self, term: str) -> list[MovieResult]:
        results = await self._get('/api/v3/movie/lookup', params={'term': term})
        return [self._map(r) for r in results[:25]]

    async def list_library(self) -> list[MovieResult]:
        """All movies currently in Radarr (for locating one to remove)."""
        results = await self._get('/api/v3/movie')
        return [self._map(r) for r in results]

    async def remove(self, movie_id: int, delete_files: bool = True) -> tuple[bool, Optional[str]]:
        try:
            await self._delete(
                f'/api/v3/movie/{movie_id}',
                params={'deleteFiles': str(delete_files).lower(), 'addImportExclusion': 'false'},
            )
            return True, None
        except Exception as exc:
            log.error(f'Failed to remove movie from Radarr: {exc}')
            return False, str(exc)

    async def add(
        self, result: MovieResult, quality_profile_id: Optional[int] = None
    ) -> tuple[bool, Optional[str]]:
        """`quality_profile_id` overrides the configured default profile for this add."""
        if result.already_added:
            return False, 'Already in Radarr.'
        try:
            profile_id = quality_profile_id if quality_profile_id is not None else await self.quality_profile_id()
        except Exception as exc:
            return False, str(exc)

        body = dict(result.raw)
        body.update({
            'qualityProfileId': profile_id,
            'rootFolderPath': self.root_folder,
            'monitored': True,
            'minimumAvailability': 'announced',
            'addOptions': {'searchForMovie': True},
        })
        try:
            await self._post('/api/v3/movie', body)
            return True, None
        except Exception as exc:
            log.error(f'Failed to add movie to Radarr: {exc}')
            return False, str(exc)

    def _map(self, r: dict) -> MovieResult:
        return MovieResult(
            id=r.get('id', 0),
            tmdb_id=r.get('tmdbId', 0),
            title=r.get('title', 'Unknown'),
            year=r.get('year'),
            overview=(r.get('overview') or '').strip(),
            poster_url=self.poster_url(r),
            already_added=bool(r.get('id')),
            raw=r,
        )
