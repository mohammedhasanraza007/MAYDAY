"""M.A.Y.D.A.Y Memory Store — Key-value context storage"""
import json, logging, time
from pathlib import Path
logger = logging.getLogger('mayday.memory.store')

class MemoryStore:
    def __init__(self, store_path: str = 'cache/memory_store.json'):
        self._path = Path(store_path)
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._data: dict = self._load()

    def _load(self) -> dict:
        if self._path.exists():
            try: return json.loads(self._path.read_text())
            except: pass
        return {'entries': {}, 'metadata': {'created': time.time()}}

    def save(self):
        self._path.write_text(json.dumps(self._data, indent=2, default=str))

    def put(self, key: str, value, ttl: int = 0):
        self._data['entries'][key] = {
            'value': value, 'timestamp': time.time(),
            'ttl': ttl, 'access_count': 0}
        self.save()

    def get(self, key: str, default=None):
        entry = self._data['entries'].get(key)
        if not entry: return default
        if entry['ttl'] > 0 and time.time() - entry['timestamp'] > entry['ttl']:
            del self._data['entries'][key]; return default
        entry['access_count'] += 1
        return entry['value']

    def delete(self, key: str):
        self._data['entries'].pop(key, None); self.save()

    def keys(self) -> list[str]:
        return list(self._data['entries'].keys())

    def clear(self):
        self._data['entries'] = {}; self.save()

    def size(self) -> int:
        return len(self._data['entries'])
