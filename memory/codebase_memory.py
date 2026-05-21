"""M.A.Y.D.A.Y Codebase Memory — Tracks file tree, deps, and state"""
import json, logging, os, time
from pathlib import Path
logger = logging.getLogger('mayday.memory.codebase')

class CodebaseMemory:
    def __init__(self, project_root: str = '.'):
        self.root = Path(project_root)
        self._file_index: dict[str, dict] = {}
        self._dependencies: dict[str, list[str]] = {}
        self._state: dict = {'last_scan': 0}

    def scan(self):
        self._file_index.clear()
        for p in self.root.rglob('*'):
            if p.is_file() and not any(x in str(p) for x in ['__pycache__', '.git', 'node_modules', 'venv']):
                rel = str(p.relative_to(self.root))
                self._file_index[rel] = {
                    'size': p.stat().st_size, 'modified': p.stat().st_mtime,
                    'extension': p.suffix, 'type': self._classify(p.suffix)}
        self._state['last_scan'] = time.time()
        self._state['total_files'] = len(self._file_index)
        logger.info(f'Scanned {len(self._file_index)} files')

    def get_file_tree(self) -> dict:
        return dict(self._file_index)

    def get_files_by_type(self, ext: str) -> list[str]:
        return [k for k, v in self._file_index.items() if v['extension'] == ext]

    def set_dependencies(self, file: str, deps: list[str]):
        self._dependencies[file] = deps

    def get_dependencies(self, file: str) -> list[str]:
        return self._dependencies.get(file, [])

    def get_summary(self) -> dict:
        types = {}
        for v in self._file_index.values():
            t = v['type']
            types[t] = types.get(t, 0) + 1
        return {**self._state, 'file_types': types}

    def _classify(self, ext: str) -> str:
        m = {'.py': 'python', '.js': 'javascript', '.ts': 'typescript',
             '.html': 'html', '.css': 'css', '.json': 'config',
             '.md': 'docs', '.txt': 'text', '.yaml': 'config', '.yml': 'config'}
        return m.get(ext, 'other')

    def export(self, path: str):
        Path(path).write_text(json.dumps({
            'file_index': self._file_index,
            'dependencies': self._dependencies,
            'state': self._state}, indent=2, default=str))
