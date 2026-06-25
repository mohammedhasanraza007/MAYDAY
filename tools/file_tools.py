"""
M.A.Y.D.A.Y File Tools — L3 FIX: Dispatches on _tool_name
"""
import hashlib
import logging, os, shutil, tempfile
from pathlib import Path
from tools.base_tool import BaseTool
from core.exceptions import ScopeViolationError

logger = logging.getLogger('mayday.tools.file')

ALLOWED_ROOTS: list[str] = []
TEXT_TEMPLATES = {
    "blank_csv": "",
    "blank_json": "{}",
    "blank_txt": "",
}

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
        p_str = str(p).lower()
        temp_root = tempfile.gettempdir().lower()
        if p_str.startswith("c:\\users") and not p_str.startswith(temp_root):
            raise ScopeViolationError("Path is inside hard-blocked directory: C:\\Users")
        if ALLOWED_ROOTS:
            if not any(str(p).startswith(r) for r in ALLOWED_ROOTS):
                raise ScopeViolationError(f'Path {p} outside allowed roots')
        return p

    def _read(self, params: dict) -> dict:
        p = self._validate_path(params.get('path', params.get('file_path', '')))
        if not p.exists():
            raise FileNotFoundError(f'File not found: {p}')
        content = p.read_text(encoding='utf-8', errors='replace')
        return {
            'status': 'success',
            'content': content,
            'path': str(p),
            'size': len(content),
            'ready': True,
            'next_step': 'Use this file content to answer, transform, or write an updated file.',
        }

    def _write(self, params: dict) -> dict:
        p = self._validate_path(params.get('path', params.get('file_path', '')))
        p.parent.mkdir(parents=True, exist_ok=True)
        template = params.get('template')
        if template == "blank_xlsx":
            import openpyxl

            wb = openpyxl.Workbook()
            wb.save(p)
            wb.close()
            if not p.exists():
                raise FileNotFoundError(f'Write verification failed; file missing: {p}')
            sha256 = hashlib.sha256(p.read_bytes()).hexdigest()
            logger.info(f'Written template: {p} ({p.stat().st_size} bytes)')
            return {
                'status': 'success',
                'state': 'written',
                'path': str(p),
                'bytes_written': p.stat().st_size,
                'bytes': p.stat().st_size,
                'exists': p.exists(),
                'sha256': sha256,
                'verified': True,
                'template': template,
                'ready': True,
                'next_step': 'Use this verified path and byte count in the final response.',
            }
        used_text_template = template in TEXT_TEMPLATES and 'content' not in params
        if used_text_template:
            content = TEXT_TEMPLATES[template]
        else:
            content = params.get('content', '')
        if not isinstance(content, str):
            raise TypeError('content must be a string')
        if not used_text_template and not content.strip():
            return {
                'status': 'error',
                'state': 'blocked_empty_content',
                'path': str(p),
                'error': 'Content is empty. Generate and validate non-empty content before calling file_write, or use an explicit blank_* template.',
                'recoverable': True,
                'next_step': 'Call generate_content first, validate minimum length, then retry file_write with content.',
            }
        if not used_text_template:
            try:
                minimum_chars = int(params.get('minimum_chars', 50))
            except (TypeError, ValueError):
                minimum_chars = 50
            if len(content.strip()) < minimum_chars:
                return {
                    'status': 'error',
                    'state': 'blocked_short_content',
                    'path': str(p),
                    'chars_written': 0,
                    'minimum_chars': minimum_chars,
                    'actual_chars': len(content.strip()),
                    'error': f'content too short: {len(content.strip())} chars; minimum is {minimum_chars}. Regenerate complete content before calling file_write.',
                    'recoverable': True,
                    'next_step': 'Regenerate complete content that satisfies minimum_chars, then retry file_write.',
                }
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
            'state': 'written',
            'path': str(p),
            'bytes_written': len(content.encode('utf-8')),
            'bytes': len(content.encode('utf-8')),
            'chars_written': len(content),
            'exists': p.exists(),
            'sha256': sha256,
            'verified': True,
            'template': template,
            'ready': True,
            'next_step': 'Use this verified path and character count in the final response.',
        }

    def _delete(self, params: dict) -> dict:
        p = self._validate_path(params.get('path', params.get('file_path', '')))
        if not p.exists():
            raise FileNotFoundError(f'Not found: {p}')
        if p.is_dir(): shutil.rmtree(p)
        else: p.unlink()
        logger.info(f'Deleted: {p}')
        return {
            'status': 'success',
            'path': str(p),
            'exists': p.exists(),
            'ready': True,
            'next_step': 'Report the deleted path or continue only if another file action is required.',
        }

    def _list(self, params: dict) -> dict:
        p = self._validate_path(params.get('path', params.get('directory', '.')))
        if not p.is_dir():
            raise NotADirectoryError(f'Not a directory: {p}')
        entries = []
        for item in sorted(p.iterdir()):
            entries.append({'name': item.name, 'type': 'dir' if item.is_dir() else 'file',
                           'size': item.stat().st_size if item.is_file() else 0})
        return {
            'status': 'success',
            'path': str(p),
            'count': len(entries),
            'entries': entries,
            'ready': True,
            'next_step': 'Use these entries to select the next file operation or answer.',
        }
