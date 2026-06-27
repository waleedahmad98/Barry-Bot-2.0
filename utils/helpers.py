_STATES = {
    'downloading': 'Downloading',
    'stalledDL': 'Stalled',
    'uploading': 'Seeding',
    'stalledUP': 'Seeding (stalled)',
    'pausedDL': 'Paused',
    'pausedUP': 'Paused (done)',
    'queuedDL': 'Queued',
    'queuedUP': 'Queued (seed)',
    'checkingDL': 'Checking',
    'checkingUP': 'Checking',
    'metaDL': 'Fetching metadata',
    'error': 'Error',
    'missingFiles': 'Missing files',
    'moving': 'Moving',
}


def format_size(size_bytes: int) -> str:
    if not size_bytes:
        return '0 B'
    n = float(size_bytes)
    for unit in ('B', 'KB', 'MB', 'GB', 'TB'):
        if n < 1024:
            return f'{n:.1f} {unit}'
        n /= 1024
    return f'{n:.1f} PB'


def progress_bar(fraction: float, length: int = 10) -> str:
    filled = round(fraction * length)
    return '█' * filled + '░' * (length - filled) + f' {fraction * 100:.1f}%'


def format_state(state: str) -> str:
    return _STATES.get(state, state)


def truncate(text: str, max_len: int) -> str:
    return text if len(text) <= max_len else text[: max_len - 1] + '…'
