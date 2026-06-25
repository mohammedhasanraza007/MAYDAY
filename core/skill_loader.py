"""
MAYDAY Skill Loader - domain-specific prompt injection.
Skills are markdown files in skills/ with optional YAML-like frontmatter.
"""
from __future__ import annotations

import logging
from pathlib import Path

logger = logging.getLogger("mayday.skills")

SKILLS_DIR = Path("skills")


class Skill:
    def __init__(self, name: str, triggers: list[str], content: str):
        self.name = name
        self.triggers = [trigger.lower() for trigger in triggers]
        self.content = content

    def matches(self, prompt: str) -> bool:
        lowered = prompt.lower()
        return any(trigger in lowered for trigger in self.triggers)


class SkillLoader:
    def __init__(self):
        self._skills: list[Skill] = []
        self._loaded = False

    def load(self, skills_dir: Path | None = None) -> int:
        directory = skills_dir or SKILLS_DIR
        directory.mkdir(exist_ok=True)
        self._skills.clear()
        count = 0
        for path in directory.glob("*.md"):
            try:
                skill = self._parse(path)
                if skill:
                    self._skills.append(skill)
                    count += 1
            except Exception as exc:
                logger.warning("Failed to load skill %s: %s", path.name, exc)
        self._loaded = True
        logger.info("Loaded %d skills from %s", count, directory)
        return count

    def _parse(self, path: Path) -> Skill | None:
        text = path.read_text(encoding="utf-8")
        triggers: list[str] = []
        content = text

        if text.startswith("---"):
            parts = text.split("---", 2)
            if len(parts) >= 3:
                frontmatter = parts[1]
                content = parts[2].strip()
                for line in frontmatter.splitlines():
                    if line.strip().startswith("triggers:"):
                        raw = line.split(":", 1)[1].strip().strip("[]")
                        triggers = [
                            item.strip().strip("\"'")
                            for item in raw.split(",")
                            if item.strip()
                        ]

        if not triggers:
            triggers = [path.stem.replace("_", " ")]

        return Skill(name=path.stem, triggers=triggers, content=content)

    def get_injections(self, prompt: str) -> str:
        if not self._loaded:
            self.load()
        matched = [skill.content for skill in self._skills if skill.matches(prompt)]
        if matched:
            return (
                "\n\n---SKILL CONTEXT---\n"
                + "\n\n".join(matched)
                + "\n---END SKILL CONTEXT---\n"
            )
        return ""

    @property
    def skill_count(self) -> int:
        return len(self._skills)


skill_loader = SkillLoader()
