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
        self,
        result: SeriesResult,
        seasons: Optional[list[int]] = None,
        quality_profile_id: Optional[int] = None,
    ) -> tuple[bool, Optional[str]]:
        """Add a series. `seasons` restricts monitoring/search to those season numbers
        (omit/None to monitor and search every season). `quality_profile_id` overrides
        the configured default profile for this add.

        This adds with nothing monitored, then does a follow-up PUT to set exact
        per-season monitoring before triggering a search — Sonarr's addOptions.monitor
        value ('all'/'none'/etc.) overrides whatever 'monitored' flags are sent on the
        `seasons` array at creation time rather than respecting them, so a custom season
        selection has to be applied as a separate update after the series exists (the
        same two-step process Sonarr's own "Season Pass" UI uses)."""
        if result.already_added:
            return False, 'Already in Sonarr.'
        try:
            profile_id = quality_profile_id if quality_profile_id is not None else await self.quality_profile_id()
        except Exception as exc:
            return False, str(exc)

        body = dict(result.raw)
        body.update({
            'qualityProfileId': profile_id,
            'rootFolderPath': self.root_folder,
            'seasonFolder': True,
            'monitored': True,
            'addOptions': {'monitor': 'none', 'searchForMissingEpisodes': False},
        })
        try:
            created = await self._post('/api/v3/series', body)
        except Exception as exc:
            log.error(f'Failed to add series to Sonarr: {exc}')
            return False, str(exc)

        wanted = None if seasons is None else set(seasons)
        for season in created.get('seasons', []):
            season['monitored'] = True if wanted is None else season.get('seasonNumber') in wanted
        created['monitored'] = True

        series_id = created.get('id')
        try:
            await self._put(f'/api/v3/series/{series_id}', created)
            await self._post('/api/v3/command', {'name': 'SeriesSearch', 'seriesId': series_id})
        except Exception as exc:
            log.error(f'Series added to Sonarr but failed to set season monitoring: {exc}')
            return False, f'Added, but failed to set season monitoring: {exc}'

        return True, None

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
