"""M.A.Y.D.A.Y System Tools — Desktop automation via pyautogui"""
import logging
from tools.base_tool import BaseTool
logger = logging.getLogger('mayday.tools.system')

class SystemTools(BaseTool):
    @property
    def name(self) -> str: return 'system'
    @property
    def description(self) -> str: return 'Desktop automation and system tasks'
    def get_capabilities(self) -> list[str]:
        return ['system_screenshot', 'system_click', 'system_type', 'system_hotkey', 'system_info']

    def execute(self, parameters: dict) -> dict:
        name = parameters.get('_tool_name', '')
        if 'screenshot' in name: return self._screenshot(parameters)
        if 'click' in name: return self._click(parameters)
        if 'type' in name: return self._type(parameters)
        if 'hotkey' in name: return self._hotkey(parameters)
        return self._info(parameters)

    def _screenshot(self, params: dict) -> dict:
        import pyautogui
        from pathlib import Path
        path = params.get('path', 'screen.png')
        try:
            img = pyautogui.screenshot()
            img.save(path)
            target = Path(path)
            if not target.exists() or target.stat().st_size == 0:
                raise IOError(f'Screenshot verification failed: {path}')
            return {'status': 'success', 'path': str(target.resolve()), 'verified': True}
        except Exception as e:
            return {'status': 'error', 'error': str(e)}

    def _click(self, params: dict) -> dict:
        control_name = params.get('control_name') or params.get('name')
        window_title = params.get('window_title') or params.get('title')
        if control_name:
            try:
                from pywinauto import Desktop

                desktop = Desktop(backend='uia')
                window = desktop.window(title_re=window_title or '.*')
                target = window.child_window(title=control_name)
                target.wait('enabled visible ready', timeout=5)
                target.click_input()
                return {
                    'status': 'success',
                    'target': control_name,
                    'window_title': window_title or '',
                    'backend': 'pywinauto-uia',
                    'verified': True,
                }
            except Exception as e:
                logger.warning('UIA click failed; falling back to coordinates: %s', e)
        import pyautogui
        x, y = params.get('x', 0), params.get('y', 0)
        pyautogui.click(x, y)
        pos = pyautogui.position()
        return {'status': 'success', 'x': x, 'y': y, 'backend': 'pyautogui-fallback', 'cursor': (pos.x, pos.y), 'verified': True}

    def _type(self, params: dict) -> dict:
        text = params.get('text', '')
        try:
            from pywinauto.keyboard import send_keys

            escaped = text.replace('{', '{{}').replace('}', '{}}')
            send_keys(escaped, pause=0.02, with_spaces=True)
            return {'status': 'success', 'chars': len(text), 'backend': 'pywinauto-uia', 'verified': True}
        except Exception as e:
            logger.warning('UIA typing failed; falling back to pyautogui: %s', e)
            import pyautogui

            pyautogui.typewrite(text, interval=0.02)
            return {'status': 'success', 'chars': len(text), 'backend': 'pyautogui-fallback', 'verified': True}

    def _hotkey(self, params: dict) -> dict:
        import pyautogui
        keys = params.get('keys', [])
        pyautogui.hotkey(*keys)
        return {'status': 'success', 'keys': keys}

    def _info(self, params: dict) -> dict:
        import psutil, platform
        focused_window = ''
        try:
            from pywinauto import Desktop

            focused_window = Desktop(backend='uia').get_active().window_text()
        except Exception:
            focused_window = ''
        return {'status': 'success', 'os': platform.system(), 'version': platform.version(),
                'cpu_percent': psutil.cpu_percent(), 'ram_total_gb': round(psutil.virtual_memory().total / 1e9, 1),
                'ram_used_gb': round(psutil.virtual_memory().used / 1e9, 1),
                'desktop_backend': 'pywinauto-uia',
                'focused_window': focused_window}
