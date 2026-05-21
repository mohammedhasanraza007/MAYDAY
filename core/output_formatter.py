import re

class ResponseFormatter:
    """
    M.A.Y.D.A.Y Response Post-Processor — v1.0
    Cleans model output, removes leaked prefixes, and ensures markdown structure.
    """

    @staticmethod
    def clean_prefixes(text: str) -> str:
        """Remove 'User:', 'Assistant:', etc. from the start of lines."""
        prefixes = ["Assistant:", "User:", "System:", "AI:"]
        lines = text.splitlines()
        cleaned_lines = []
        for line in lines:
            temp_line = line.strip()
            for p in prefixes:
                if temp_line.startswith(p):
                    line = temp_line[len(p):].strip()
                    break
            cleaned_lines.append(line)
        return "\n".join(cleaned_lines).strip()

    @staticmethod
    def normalize_whitespace(text: str) -> str:
        """Ensure consistent double newlines between paragraphs and code blocks."""
        # Normalize newlines
        text = text.replace('\r\n', '\n')
        
        parts = text.split("```")
        new_parts = []
        
        for i, part in enumerate(parts):
            if i % 2 == 0:
                # Text outside code blocks
                # Remove triple+ newlines
                p = re.sub(r'\n{3,}', '\n\n', part)
                new_parts.append(p.strip())
            else:
                # Content inside code blocks (including lang id)
                # Ensure it doesn't have leading/trailing whitespace that breaks formatting
                # but keep the language ID line intact
                new_parts.append(part.strip())
        
        # Reassemble
        result = ""
        for i, part in enumerate(new_parts):
            if i % 2 == 0:
                if part:
                    if i > 0:
                        result += "\n\n" + part
                    else:
                        result += part
            else:
                # Wrap code block
                # If there's a language id, it's the first word/line
                # Ensure it looks like: \n\n```python\ncode\n```\n\n
                if i > 0:
                    result = result.rstrip() + "\n\n```"
                else:
                    result += "```"
                
                result += part + "```"
        
        return result.strip()

    @staticmethod
    def fix_markdown(text: str) -> str:
        """Fix common broken markdown issues."""
        # Ensure closing backticks if missing
        if text.count("```") % 2 != 0:
            text += "\n```"
        return text

    @classmethod
    def format(cls, text: str) -> str:
        """Run the full cleanup pipeline."""
        if not text:
            return ""
        
        text = cls.clean_prefixes(text)
        text = cls.fix_markdown(text)
        text = cls.normalize_whitespace(text)
        
        return text
