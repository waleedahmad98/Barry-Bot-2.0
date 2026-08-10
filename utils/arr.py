import logging
from typing import Optional

import aiohttp

log = logging.getLogger('mediabot.arr')


class ArrClient:
    """Shared base for Radarr/Sonarr — both are Servarr apps with near-identical APIs."""

    def __init__(self, host: str, port: int, api_key: str, quality_profile: str, root_folder: str):
        self.base_url = f'{host}:{port}'
        self.api_key = api_key
        self.quality_profile_name = quality_profile
        self.root_folder = root_folder
        self._quality_profile_id: Optional[int] = None

    def _headers(self) -> dict:
        return {'X-Api-Key': self.api_key}

    async def _get(self, path: str, params: Optional[dict] = None):
        timeout = aiohttp.ClientTimeout(total=20)
        async with aiohttp.ClientSession(timeout=timeout, headers=self._headers()) as session:
            async with session.get(f'{self.base_url}{path}', params=params) as resp:
                resp.raise_for_status()
                return await resp.json()

    async def _post(self, path: str, json_body: dict):
        timeout = aiohttp.ClientTimeout(total=20)
        async with aiohttp.ClientSession(timeout=timeout, headers=self._headers()) as session:
            async with session.post(f'{self.base_url}{path}', json=json_body) as resp:
                if resp.status not in (200, 201):
                    text = await resp.text()
                    raise RuntimeError(f'{path} failed ({resp.status}): {text}')
                return await resp.json()

    async def connect(self) -> bool:
        try:
            await self._get('/api/v3/system/status')
            log.info(f'Connected to {type(self).__name__}')
            return True
        except Exception as exc:
            log.warning(f'{type(self).__name__} connection failed: {exc}')
            return False

    async def quality_profile_id(self) -> int:
        if self._quality_profile_id is None:
            profiles = await self._get('/api/v3/qualityprofile')
            match = next(
                (p for p in profiles if p['name'].lower() == self.quality_profile_name.lower()), None
            )
            if not match:
                available = ', '.join(p['name'] for p in profiles)
                raise ValueError(
                    f'Quality profile "{self.quality_profile_name}" not found. Available: {available}'
                )
            self._quality_profile_id = match['id']
        return self._quality_profile_id

    @staticmethod
    def poster_url(item: dict) -> Optional[str]:
        return next(
            (i.get('remoteUrl') for i in item.get('images', []) if i.get('coverType') == 'poster'),
            None,
        )
