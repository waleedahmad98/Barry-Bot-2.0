import asyncio
import logging
import shutil
from dataclasses import dataclass
from pathlib import Path

log = logging.getLogger('mediabot.files')


@dataclass
class MediaEntry:
    """One top-level file or folder under a paths.movies/paths.shows directory."""

    name: str
    path: str
    is_dir: bool
    size: int


def _dir_size(path: Path) -> int:
    return sum(p.stat().st_size for p in path.rglob('*') if p.is_file())


async def find(root: str, query: str) -> list[MediaEntry]:
    """Top-level entries directly under `root` whose name contains `query`."""
    base = Path(root)
    if not base.is_dir():
        return []

    def _scan() -> list[MediaEntry]:
        q = query.lower()
        entries = []
        for child in base.iterdir():
            if q not in child.name.lower():
                continue
            is_dir = child.is_dir()
            size = _dir_size(child) if is_dir else child.stat().st_size
            entries.append(MediaEntry(name=child.name, path=str(child), is_dir=is_dir, size=size))
        return entries

    return await asyncio.to_thread(_scan)


async def delete(entry: MediaEntry):
    p = Path(entry.path)
    if entry.is_dir:
        await asyncio.to_thread(shutil.rmtree, p)
        log.info(f'Deleted directory: {p}')
    else:
        await asyncio.to_thread(p.unlink)
        log.info(f'Deleted file: {p}')
        try:
            await asyncio.to_thread(p.parent.rmdir)
            log.info(f'Removed empty folder: {p.parent}')
        except OSError:
            pass  # folder not empty (extras, subtitles, etc.)
