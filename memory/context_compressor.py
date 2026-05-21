"""M.A.Y.D.A.Y Context Compressor — Rolling summaries and token budgeting (L23)"""
import logging
logger = logging.getLogger('mayday.memory.compressor')

class ContextCompressor:
    def __init__(self, max_tokens: int = 3800):
        self.max_tokens = max_tokens
        self._summaries: list[str] = []

    def compress(self, history: list[dict]) -> str:
        """Compress history to fit within token budget."""
        parts = []
        token_count = 0
        for entry in reversed(history):
            content = entry.get('content', '')
            tokens = len(content.split())
            if token_count + tokens > self.max_tokens:
                # Summarize older entries
                summary = self._summarize_entry(content)
                parts.insert(0, summary)
                token_count += len(summary.split())
            else:
                parts.insert(0, content)
                token_count += tokens
        return '\n'.join(parts)

    def _summarize_entry(self, content: str) -> str:
        words = content.split()
        if len(words) <= 50: return content
        return ' '.join(words[:25]) + ' [...] ' + ' '.join(words[-25:])

    def add_frozen_summary(self, summary: str):
        self._summaries.append(summary)

    def get_architecture_context(self) -> str:
        return '\n'.join(self._summaries)
