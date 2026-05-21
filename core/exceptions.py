"""
M.A.Y.D.A.Y Core Exceptions — E001 through E021
=================================================
ALL exception classes are defined HERE and ONLY here.
No other file in the project may define exception classes.
Every exception carries a .code attribute for structured logging.

v4.1 audit compliance: This is generation order file #1.
"""


class MAYDAYError(Exception):
    """Base exception for all M.A.Y.D.A.Y errors."""
    code: str = 'E000'

    def __init__(self, message: str = '', **kwargs):
        self.message = message
        self.details = kwargs
        super().__init__(f'[{self.code}] {message}')


# ─── Hard Rules & Inference ──────────────────────────────────────────────────

class HardRuleViolationError(MAYDAYError):
    """E001 — A HARD_RULE was about to be broken."""
    code = 'E001'


class InferenceTimeoutError(MAYDAYError):
    """E002 — Local model timed out (90s with API / 180s without)."""
    code = 'E002'


class ParseError(MAYDAYError):
    """E003 — Model output could not be parsed as valid JSON."""
    code = 'E003'


class SchemaValidationError(MAYDAYError):
    """E004 — JSON valid but does not match ACTION_SCHEMA."""
    code = 'E004'


# ─── Security & Permissions ──────────────────────────────────────────────────

class ScopeViolationError(MAYDAYError):
    """E005 — File path outside ALLOWED_FILE_SCOPE_ROOTS."""
    code = 'E005'


class PermissionDeniedError(MAYDAYError):
    """E006 — User denied or timed out on permission prompt (30s)."""
    code = 'E006'


# ─── Tool Execution ─────────────────────────────────────────────────────────

class ToolTimeoutError(MAYDAYError):
    """E007 — Tool execution exceeded 30 second ThreadPoolExecutor limit."""
    code = 'E007'


class BrowserDepthError(MAYDAYError):
    """E008 — Browser navigation exceeded max depth 5."""
    code = 'E008'


# ─── Agent Loop Guards ───────────────────────────────────────────────────────

class RecursiveCallError(MAYDAYError):
    """E009 — inference_depth > 1 — model tried to call itself."""
    code = 'E009'


class SessionLimitError(MAYDAYError):
    """E010 — Session exceeded 50 agent loop steps."""
    code = 'E010'


# ─── Packaging & Stability ───────────────────────────────────────────────────

class ZipBlockedError(MAYDAYError):
    """E011 — PackagingLayer.package() called before ExecutionGate cleared."""
    code = 'E011'


class StabilityWindowError(MAYDAYError):
    """E012 — ZIP attempted before 3-consecutive-pass window confirmed."""
    code = 'E012'


class HealthScoreBelowThreshold(MAYDAYError):
    """E013 — HealthMonitor.compute_score() returned < 85."""
    code = 'E013'


# ─── Runtime & Engine ────────────────────────────────────────────────────────

class EngineMissingError(MAYDAYError):
    """E014 — runtime/engine.py not found at bootstrap — critical."""
    code = 'E014'


class ScaffoldError(MAYDAYError):
    """E015 — ScaffoldEngine failed atomic write — rolled back entirely."""
    code = 'E015'


class ServerStartError(MAYDAYError):
    """E016 — Generated project server failed to respond within 15 seconds."""
    code = 'E016'


class DevLoopExhaustedError(MAYDAYError):
    """E017 — ContinuousDevLoop hit max 5 debug cycles — debug_report.txt written."""
    code = 'E017'


class MemoryBudgetExceededError(MAYDAYError):
    """E018 — RSS > 4.5 GB after emergency cleanup — session halted."""
    code = 'E018'


# ─── Provider & Web ──────────────────────────────────────────────────────────

class ProviderFailureError(MAYDAYError):
    """E019 — API provider call failed — ModelRouter fallback triggered."""
    code = 'E019'


class WebAccessDisabledError(MAYDAYError):
    """E020 — Search/fetch attempted with web toggle in OFF state."""
    code = 'E020'


# ─── Critical Model ─────────────────────────────────────────────────────────

class CriticalModelError(MAYDAYError):
    """E021 — All 3 model tiers (4B→3B→1.5B) failed to load."""
    code = 'E021'


# ─── Lookup Table ────────────────────────────────────────────────────────────

ERROR_CODE_MAP: dict[str, type[MAYDAYError]] = {
    'E001': HardRuleViolationError,
    'E002': InferenceTimeoutError,
    'E003': ParseError,
    'E004': SchemaValidationError,
    'E005': ScopeViolationError,
    'E006': PermissionDeniedError,
    'E007': ToolTimeoutError,
    'E008': BrowserDepthError,
    'E009': RecursiveCallError,
    'E010': SessionLimitError,
    'E011': ZipBlockedError,
    'E012': StabilityWindowError,
    'E013': HealthScoreBelowThreshold,
    'E014': EngineMissingError,
    'E015': ScaffoldError,
    'E016': ServerStartError,
    'E017': DevLoopExhaustedError,
    'E018': MemoryBudgetExceededError,
    'E019': ProviderFailureError,
    'E020': WebAccessDisabledError,
    'E021': CriticalModelError,
}

__all__ = [
    'MAYDAYError',
    'HardRuleViolationError',
    'InferenceTimeoutError',
    'ParseError',
    'SchemaValidationError',
    'ScopeViolationError',
    'PermissionDeniedError',
    'ToolTimeoutError',
    'BrowserDepthError',
    'RecursiveCallError',
    'SessionLimitError',
    'ZipBlockedError',
    'StabilityWindowError',
    'HealthScoreBelowThreshold',
    'EngineMissingError',
    'ScaffoldError',
    'ServerStartError',
    'DevLoopExhaustedError',
    'MemoryBudgetExceededError',
    'ProviderFailureError',
    'WebAccessDisabledError',
    'CriticalModelError',
    'ERROR_CODE_MAP',
]
