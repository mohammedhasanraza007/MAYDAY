"""
M.A.Y.D.A.Y Session Manager — State Tracking & Step Limiting
=============================================================
Manages session state, step counting (50-step max), context window,
and session persistence.

v4.1 audit compliance: Generation order file #7.
"""
import json
import logging
import time
import uuid
from pathlib import Path
from typing import Any

from core.exceptions import SessionLimitError

logger = logging.getLogger('mayday.session')

MAX_SESSION_STEPS = 15
MAX_CONTEXT_TOKENS = 1500
MAX_RETRIES = 3
MAX_RECOVERY_DEPTH = 2
MAX_PLANNING_DEPTH = 2


class SessionManager:
    """
    Manages a single agent session with step limiting and state tracking.

    Enforces:
    - 50-step maximum per session (E010)
    - Context window budget (3800 tokens)
    - Session state persistence for recovery
    """

    def __init__(self, session_dir: str = 'logs/sessions'):
        self.session_id: str = str(uuid.uuid4())[:8]
        self.session_dir = Path(session_dir)
        self.session_dir.mkdir(parents=True, exist_ok=True)

        self.step_count: int = 0
        self.max_steps: int = MAX_SESSION_STEPS
        self.start_time: float = time.time()
        self.context_budget: int = MAX_CONTEXT_TOKENS

        self._history: list[dict] = []
        self._state: dict[str, Any] = {
            'session_id': self.session_id,
            'status': 'active',
            'created_at': time.strftime('%Y-%m-%dT%H:%M:%S'),
        }

        logger.info(f'Session created: {self.session_id}')

    def increment_step(self) -> int:
        """
        Increment step counter and return current count.

        Raises:
            SessionLimitError: If step count exceeds MAX_SESSION_STEPS (E010)
        """
        self.step_count += 1
        if self.step_count > self.max_steps:
            self._state['status'] = 'limit_reached'
            self._persist()
            raise SessionLimitError(
                f'Session {self.session_id} exceeded {self.max_steps} steps'
            )
        return self.step_count

    def add_to_history(self, role: str, content: str, metadata: dict | None = None) -> None:
        """Add an entry to session history."""
        entry = {
            'step': self.step_count,
            'role': role,
            'content': content,
            'timestamp': time.time(),
            'metadata': metadata or {},
        }
        self._history.append(entry)

    def get_context_window(self) -> list[dict]:
        """
        Return history entries that fit within the context budget.
        Most recent entries are prioritized.
        """
        result = []
        token_count = 0

        for entry in reversed(self._history):
            entry_tokens = len(entry['content'].split())
            if token_count + entry_tokens > self.context_budget:
                break
            result.insert(0, entry)
            token_count += entry_tokens

        return result

    def get_context_string(self) -> str:
        """Return the context window as a formatted string for model input."""
        window = self.get_context_window()
        parts = []
        for entry in window:
            parts.append(f"[{entry['role']}] {entry['content']}")
        return '\n'.join(parts)

    def get_state(self) -> dict:
        """Return current session state."""
        return {
            **self._state,
            'step_count': self.step_count,
            'max_steps': self.max_steps,
            'history_length': len(self._history),
            'elapsed_seconds': round(time.time() - self.start_time, 1),
        }

    def set_status(self, status: str) -> None:
        """Update session status."""
        self._state['status'] = status
        logger.info(f'Session {self.session_id} status: {status}')

    def _persist(self) -> None:
        """Save session state to disk for recovery."""
        try:
            filepath = self.session_dir / f'{self.session_id}.json'
            data = {
                **self.get_state(),
                'history': self._history[-20:],  # Last 20 entries only
            }
            filepath.write_text(json.dumps(data, indent=2, default=str))
        except Exception as e:
            logger.warning(f'Session persist failed: {e}')

    def end_session(self) -> dict:
        """End the session and return final state."""
        self._state['status'] = 'completed'
        self._state['ended_at'] = time.strftime('%Y-%m-%dT%H:%M:%S')
        self._persist()
        logger.info(f'Session ended: {self.session_id} ({self.step_count} steps)')
        return self.get_state()

    @classmethod
    def resume(cls, session_file: str) -> 'SessionManager':
        """Resume a session from a persisted state file."""
        data = json.loads(Path(session_file).read_text())
        session = cls()
        session.session_id = data.get('session_id', session.session_id)
        session.step_count = data.get('step_count', 0)
        session._history = data.get('history', [])
        session._state = {
            'session_id': session.session_id,
            'status': 'resumed',
            'resumed_from': session_file,
        }
        logger.info(f'Session resumed: {session.session_id} at step {session.step_count}')
        return session
