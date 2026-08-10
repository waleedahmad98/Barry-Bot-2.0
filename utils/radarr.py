import logging
from dataclasses import dataclass, field
from typing import Optional

from utils.arr import ArrClient

log = logging.getLogger('mediabot.radarr')


@dataclass
class MovieResult:
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

    async def add(self, result: MovieResult) -> tuple[bool, Optional[str]]:
        if result.already_added:
            return False, 'Already in Radarr.'
        try:
            profile_id = await self.quality_profile_id()
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
            tmdb_id=r.get('tmdbId', 0),
            title=r.get('title', 'Unknown'),
            year=r.get('year'),
            overview=(r.get('overview') or '').strip(),
            poster_url=self.poster_url(r),
            already_added=bool(r.get('id')),
            raw=r,
        )
