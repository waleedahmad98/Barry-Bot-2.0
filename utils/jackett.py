import xml.etree.ElementTree as ET
from dataclasses import dataclass
from typing import Optional

import aiohttp

_NS = 'http://torznab.com/schemas/2015/feed'

CATEGORIES = {
    'movies': [2000, 2010, 2020, 2030, 2040, 2045],
    'shows': [5000, 5030, 5040, 5045],
    'all': [],
}


@dataclass
class TorrentResult:
    title: str
    size: int
    seeders: int
    leechers: int
    link: str
    magnet: Optional[str]
    indexer: str
    guid: str

    @property
    def download_url(self) -> Optional[str]:
        return self.magnet or (self.link if self.link else None)


class JackettClient:
    def __init__(self, host: str, port: int, api_key: str, indexer: str = 'all'):
        self.base_url = f'{host}:{port}'
        self.api_key = api_key
        self.indexer = indexer

    async def search(
        self, query: str, category: str = 'all', limit: int = 25
    ) -> list[TorrentResult]:
        cats = CATEGORIES.get(category, [])
        params: dict = {'apikey': self.api_key, 't': 'search', 'q': query, 'limit': limit}
        if cats:
            params['cat'] = ','.join(map(str, cats))

        url = f'{self.base_url}/api/v2.0/indexers/{self.indexer}/results/torznab'
        timeout = aiohttp.ClientTimeout(total=30)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.get(url, params=params) as resp:
                resp.raise_for_status()
                text = await resp.text()

        results = self._parse(text)
        results.sort(key=lambda r: r.seeders, reverse=True)
        return results

    def _parse(self, xml_text: str) -> list[TorrentResult]:
        try:
            root = ET.fromstring(xml_text)
        except ET.ParseError:
            return []

        channel = root.find('channel')
        if channel is None:
            return []

        results = []
        for item in channel.findall('item'):
            title = item.findtext('title', '')
            link = item.findtext('link', '')
            guid = item.findtext('guid', '')

            attrs: dict[str, str] = {
                a.get('name', ''): a.get('value', '')
                for a in item.findall(f'{{{_NS}}}attr')
            }

            enc = item.find('enclosure')
            enc_url = enc.get('url', '') if enc is not None else ''

            raw_size = attrs.get('size') or item.findtext('size', '0') or '0'
            size = int(raw_size) if raw_size.isdigit() else 0

            results.append(
                TorrentResult(
                    title=title,
                    size=size,
                    seeders=int(attrs.get('seeders', 0)),
                    leechers=int(attrs.get('leechers', 0)),
                    link=enc_url or link,
                    magnet=attrs.get('magneturl'),
                    indexer=attrs.get('indexer', 'Unknown'),
                    guid=guid,
                )
            )
        return results
