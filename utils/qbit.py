import asyncio
import logging
from dataclasses import dataclass
from typing import Optional

import qbittorrentapi

log = logging.getLogger('mediabot.qbit')


@dataclass
class TorrentInfo:
    name: str
    hash: str
    progress: float
    size: int
    state: str
    save_path: str
    num_seeds: int
    num_leechs: int
    eta: int


class QBitClient:
    def __init__(self, host: str, port: int, username: str, password: str):
        self._client = qbittorrentapi.Client(
            host=f'{host}:{port}',
            username=username,
            password=password,
            REQUESTS_ARGS={'timeout': 10},
            VERIFY_WEBUI_CERTIFICATE=False,
        )

    async def connect(self) -> bool:
        try:
            await asyncio.to_thread(self._client.auth_log_in)
            log.info('Connected to qBittorrent')
            return True
        except Exception as exc:
            log.warning(f'qBittorrent connection failed: {exc}')
            return False

    async def add_torrent(self, url: str, save_path: Optional[str] = None) -> bool:
        kwargs: dict = {'urls': url}
        if save_path:
            kwargs['save_path'] = save_path
        try:
            result = await asyncio.to_thread(self._client.torrents_add, **kwargs)
            return result == 'Ok.'
        except Exception as exc:
            log.error(f'Failed to add torrent: {exc}')
            return False

    async def list_torrents(self, status_filter: str = 'all') -> list[TorrentInfo]:
        torrents = await asyncio.to_thread(
            self._client.torrents_info, status_filter=status_filter
        )
        return [self._map(t) for t in torrents]

    async def get_torrent(self, torrent_hash: str) -> Optional[TorrentInfo]:
        torrents = await asyncio.to_thread(
            self._client.torrents_info, torrent_hashes=torrent_hash
        )
        return self._map(torrents[0]) if torrents else None

    async def pause(self, torrent_hash: str):
        await asyncio.to_thread(self._client.torrents_pause, torrent_hashes=torrent_hash)

    async def resume(self, torrent_hash: str):
        await asyncio.to_thread(self._client.torrents_resume, torrent_hashes=torrent_hash)

    async def remove(self, torrent_hash: str, delete_files: bool = False):
        await asyncio.to_thread(
            self._client.torrents_delete,
            delete_files=delete_files,
            torrent_hashes=torrent_hash,
        )

    def _map(self, t) -> TorrentInfo:
        return TorrentInfo(
            name=t.name,
            hash=t.hash,
            progress=t.progress,
            size=t.size,
            state=t.state,
            save_path=t.save_path,
            num_seeds=t.num_seeds,
            num_leechs=t.num_leechs,
            eta=t.eta,
        )
