import logging
from dataclasses import dataclass, field
from typing import Optional

from utils.arr import ArrClient

log = logging.getLogger('mediabot.sonarr')


@dataclass
class SeriesResult:
    id: int
    tvdb_id: int
    title: str
    year: Optional[int]
    overview: str
    poster_url: Optional[str]
    already_added: bool
    raw: dict = field(repr=False)


class SonarrClient(ArrClient):
    async def lookup(self, term: str) -> list[SeriesResult]:
        results = await self._get('/api/v3/series/lookup', params={'term': term})
        return [self._map(r) for r in results[:25]]

    async def list_library(self) -> list[SeriesResult]:
        """All series currently in Sonarr (for locating one to remove)."""
        results = await self._get('/api/v3/series')
        return [self._map(r) for r in results]

    async def remove(self, series_id: int, delete_files: bool = True) -> tuple[bool, Optional[str]]:
        try:
            await self._delete(
                f'/api/v3/series/{series_id}',
                params={'deleteFiles': str(delete_files).lower(), 'addImportListExclusion': 'false'},
            )
            return True, None
        except Exception as exc:
            log.error(f'Failed to remove series from Sonarr: {exc}')
            return False, str(exc)

    async def add(
        self, result: SeriesResult, seasons: Optional[list[int]] = None
    ) -> tuple[bool, Optional[str]]:
        """Add a series. `seasons` restricts monitoring/search to those season numbers;
        omit (or pass None) to monitor and search every season."""
        if result.already_added:
            return False, 'Already in Sonarr.'
        try:
            profile_id = await self.quality_profile_id()
        except Exception as exc:
            return False, str(exc)

        body = dict(result.raw)
        season_list = body.get('seasons', [])
        if seasons is None:
            for season in season_list:
                season['monitored'] = True
            monitor_option = 'all'
        else:
            wanted = set(seasons)
            for season in season_list:
                season['monitored'] = season.get('seasonNumber') in wanted
            monitor_option = 'none'  # let the per-season 'monitored' flags above drive it
        body.update({
            'qualityProfileId': profile_id,
            'rootFolderPath': self.root_folder,
            'seasonFolder': True,
            'monitored': True,
            'seasons': season_list,
            'addOptions': {'monitor': monitor_option, 'searchForMissingEpisodes': True},
        })
        try:
            await self._post('/api/v3/series', body)
            return True, None
        except Exception as exc:
            log.error(f'Failed to add series to Sonarr: {exc}')
            return False, str(exc)

    def _map(self, r: dict) -> SeriesResult:
        return SeriesResult(
            id=r.get('id', 0),
            tvdb_id=r.get('tvdbId', 0),
            title=r.get('title', 'Unknown'),
            year=r.get('year'),
            overview=(r.get('overview') or '').strip(),
            poster_url=self.poster_url(r),
            already_added=bool(r.get('id')),
            raw=r,
        )
