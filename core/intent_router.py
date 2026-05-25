from __future__ import annotations

import re


TRIGGERS = {
    "WEB_ACCESS": [
        "search for",
        "web search",
        "fetch ",
        "fetch title",
        "page fetch",
        "look up",
        "find ",
        "pc build",
        "gpu",
        "cpu",
        "hardware",
        "laptop",
        "phone",
        "google",
        "julias ai",
        "julia's ai",
        "julia",
    ],
    "PROJECT_CREATION": [
        "make app",
        "create project",
        "build website",
        "generate backend",
        "implement system",
        "scaffold",
        "build me a",
        "calculator app",
        "pyqt",
        "pyqt5",
        "pyqt6",
        "tkinter",
        "gui app",
        "game",
        "workflow",
        "n8n",
        "flappy",
        "flappy bird",
    ],
    "EXECUTION": [
        "run",
        "execute",
        "launch",
        "start server",
        "test app",
    ],
    "AUTOMATION": [
        "open ",
        "schedule",
        "book",
        "login",
        "upload",
        "fill form",
        "google meet",
        "gmail",
        "calendar",
        "click",
        "type",
        "fill",
        "navigate",
        "press",
        "session",
        "play",
        "whatsapp",
        "whats app",
    ],
    "FILE_OPS": [
        "create file",
        "write file",
        "edit file",
        "modify",
        "patch",
        "rewrite",
        "refactor",
        "open this file",
        "read file",
        "open file",
        "read it",
        "make a new file",
        "make file",
        "excel file",
        "spreadsheet",
        ".xlsx",
    ],
}


REQUIRED_TOOLS = {
    "WEB_ACCESS": ["web_search", "web_fetch"],
    "PROJECT_CREATION": ["scaffold", "file_write"],
    "EXECUTION": ["shell_run", "server_runner"],
    "AUTOMATION": ["browser_automation", "playwright_runner"],
    "FILE_OPS": ["file_tools", "diff_engine"],
}


TOKEN_PATTERN = re.compile(r"[a-z0-9_]+")


SEMANTIC_KEYWORDS = {
    "WEB_ACCESS": {
        "verbs": {"search", "fetch", "look"},
        "nouns": {"web", "page", "url", "website", "title", "site"},
    },
    "PROJECT_CREATION": {
        "verbs": {"build", "create", "generate", "make", "scaffold", "implement", "write", "setup"},
        "nouns": {"app", "project", "api", "backend", "website", "service", "config", "json", "calculator", "gui", "pyqt", "pyqt6", "pyqt5", "tkinter", "game", "flappy", "bird", "workflow", "n8n"},
    },
    "EXECUTION": {
        "verbs": {"run", "execute", "launch", "start", "test", "deploy"},
        "nouns": {"server", "tests", "app", "service"},
    },
    "AUTOMATION": {
        "verbs": {"open", "schedule", "book", "login", "search", "upload", "fill", "click", "type", "press", "navigate", "wait"},
        "nouns": {"gmail", "calendar", "meet", "form", "browser", "google", "youtube", "brave", "field", "button", "input", "session", "page"},
    },
    "FILE_OPS": {
        "verbs": {"fix", "edit", "modify", "patch", "rewrite", "refactor", "update", "create", "write"},
        "nouns": {"bug", "file", "code", "module", "script", "excel", "spreadsheet", "workbook", "xlsx"},
    },
}


def classify(prompt: str) -> str | None:
    text = (prompt or "").lower()

    # Priority: native GUI/desktop app creation takes precedence over
    # AUTOMATION or EXECUTION keywords that might also appear in the prompt.
    if re.search(r"\b(?:pyqt|pyqt5|pyqt6|tkinter|wxpython|kivy)\b", text) and re.search(
        r"\b(?:create|make|build|scaffold|generate|implement|calculator|app|gui|game)\b", text
    ):
        return "PROJECT_CREATION"

    if any(k in text for k in ("browser", "playwright", "chrome", "brave")):
        return "AUTOMATION"

    if re.search(r"\b(?:click|type|fill|press|navigate|wait|select)\b", text) and re.search(
        r"\b(?:field|button|input|bar|link|box|text|enter|email|phone|gmail|youtube|google|search|session|page)\b", text
    ):
        return "AUTOMATION"

    if re.search(r"\b(?:create|write|make)\s+(?:a\s+)?file\b", text):
        return "FILE_OPS"
    if re.search(r"\bopen\b", text) and re.search(r"\bsearch\b", text) and (
        "google" in text or re.search(r"https?://|(?:www\.)?[a-z0-9.-]+\.[a-z]{2,}", text)
    ):
        return "AUTOMATION"
    if re.search(r"\bfetch\b", text) and (
        re.search(r"https?://|(?:www\.)?[a-z0-9.-]+\.[a-z]{2,}", text) or "title" in text
    ):
        return "WEB_ACCESS"
    if re.search(r"\bsearch\s+(?:for\s+)?", text):
        return "WEB_ACCESS"
    if re.search(r"\b(?:gpu|cpu|hardware|pc build|gaming pc|laptop|phone|rtx|50 series)\b", text):
        return "WEB_ACCESS"

    # Rule-first matching for explicit phrases from the handoff contract.
    # Sort phrases by length descending to match longest specific rules first (e.g. "open file" before "open ")
    all_phrases = []
    for family, phrases in TRIGGERS.items():
        for phrase in phrases:
            all_phrases.append((phrase, family))
    all_phrases.sort(key=lambda x: len(x[0]), reverse=True)

    for phrase, family in all_phrases:
        if phrase in text:
            return family

    # Semantic fallback for natural phrasing that misses exact trigger strings.
    tokens = set(TOKEN_PATTERN.findall(text))
    if not tokens:
        return None

    scores: dict[str, int] = {}
    verb_hits_by_family: dict[str, int] = {}
    for family, rules in SEMANTIC_KEYWORDS.items():
        verb_hits = len(tokens & rules["verbs"])
        noun_hits = len(tokens & rules["nouns"])
        # Prefer intents where we have both action + target context.
        score = (verb_hits * 2) + noun_hits
        if verb_hits > 0 and noun_hits > 0:
            score += 2
        scores[family] = score
        verb_hits_by_family[family] = verb_hits

    best_family = max(scores, key=scores.get)
    if scores[best_family] <= 0:
        return None
    if verb_hits_by_family.get(best_family, 0) == 0:
        return None
    if best_family == "FILE_OPS":
        noun_hits = len(tokens & SEMANTIC_KEYWORDS["FILE_OPS"]["nouns"])
        if noun_hits == 0:
            return None
    if best_family == "PROJECT_CREATION":
        noun_hits = len(tokens & SEMANTIC_KEYWORDS["PROJECT_CREATION"]["nouns"])
        if noun_hits == 0:
            return None
    return best_family


def required_tools_for(prompt: str) -> list[str]:
    family = classify(prompt)
    if family is None:
        return []
    return REQUIRED_TOOLS.get(family, [])


def is_executable_intent(prompt: str) -> bool:
    return classify(prompt) is not None
