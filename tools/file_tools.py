"""
M.A.Y.D.A.Y File Tools — L3 FIX: Dispatches on _tool_name
"""
import hashlib
import logging, os, shutil
from pathlib import Path
from tools.base_tool import BaseTool
from core.exceptions import ScopeViolationError

logger = logging.getLogger('mayday.tools.file')

ALLOWED_ROOTS: list[str] = []

def set_file_roots(roots: list[str]):
    global ALLOWED_ROOTS
    ALLOWED_ROOTS = [os.path.abspath(r) for r in roots]


class FileTools(BaseTool):
    @property
    def name(self) -> str: return 'file'
    @property
    def description(self) -> str: return 'File read/write/delete/list operations'

    def get_capabilities(self) -> list[str]:
        return ['file_read', 'file_write', 'file_delete', 'file_list']

    def execute(self, parameters: dict) -> dict:
        # L3 FIX: dispatch on _tool_name
        name = parameters.get('_tool_name', '')
        if 'write' in name:  return self._write(parameters)
        if 'delete' in name: return self._delete(parameters)
        if 'list' in name:   return self._list(parameters)
        return self._read(parameters)

    def _validate_path(self, path: str) -> Path:
        p = Path(path).resolve()
        if ALLOWED_ROOTS:
            if not any(str(p).startswith(r) for r in ALLOWED_ROOTS):
                raise ScopeViolationError(f'Path {p} outside allowed roots')
        return p

    def _read(self, params: dict) -> dict:
        p = self._validate_path(params.get('path', params.get('file_path', '')))
        if not p.exists():
            raise FileNotFoundError(f'File not found: {p}')
        content = p.read_text(encoding='utf-8', errors='replace')
        return {'status': 'success', 'content': content, 'path': str(p), 'size': len(content)}

    def _write(self, params: dict) -> dict:
        p = self._validate_path(params.get('path', params.get('file_path', '')))
        content = params.get('content', '')
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding='utf-8')
        if not p.exists():
            raise FileNotFoundError(f'Write verification failed; file missing: {p}')
        actual = p.read_text(encoding='utf-8', errors='replace')
        if actual != content:
            raise IOError(f'Write verification failed; content mismatch: {p}')
        sha256 = hashlib.sha256(p.read_bytes()).hexdigest()
        logger.info(f'Written: {p} ({len(content)} chars)')
        return {
            'status': 'success',
            'path': str(p),
            'bytes_written': len(content.encode('utf-8')),
            'chars_written': len(content),
            'sha256': sha256,
            'verified': True,
        }

    def _delete(self, params: dict) -> dict:
        p = self._validate_path(params.get('path', params.get('file_path', '')))
        if not p.exists():
            raise FileNotFoundError(f'Not found: {p}')
        if p.is_dir(): shutil.rmtree(p)
        else: p.unlink()
        logger.info(f'Deleted: {p}')
        return {'status': 'success', 'path': str(p)}

    def _list(self, params: dict) -> dict:
        p = self._validate_path(params.get('path', params.get('directory', '.')))
        if not p.is_dir():
            raise NotADirectoryError(f'Not a directory: {p}')
        entries = []
        for item in sorted(p.iterdir()):
            entries.append({'name': item.name, 'type': 'dir' if item.is_dir() else 'file',
                           'size': item.stat().st_size if item.is_file() else 0})
        return {'status': 'success', 'path': str(p), 'entries': entries}
