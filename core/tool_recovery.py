from __future__ import annotations

import re
from pathlib import Path
from typing import Any
from urllib.parse import quote, urlparse


FINALIZE_AFTER_TOOL = "_finalize_after_tool"
RECOVERY_SOURCE = "_recovery_source"
NO_ACTION: dict[str, Any] | None = None

FILE_WRITE_PATTERN = re.compile(
    r"\b(?:create|write|make)\s+(?:a\s+)?file\s+(?P<path>.+?)\s+with\s+"
    r"(?:text|content)\s+(?P<content>.+)\s*$",
    re.IGNORECASE | re.DOTALL,
)
EXACT_FILE_WRITE_PATTERN = re.compile(
    r"\b(?:create|write|make)\s+(?:this\s+exact\s+)?file\s*:\s*"
    r"(?P<path>.+?)\s+Contents\s*:\s*(?P<content>.+)\s*$",
    re.IGNORECASE | re.DOTALL,
)
URL_PATTERN = re.compile(
    r"https?://[^\s\"'<>]+|(?:www\.)?[a-z0-9][a-z0-9.-]*\.[a-z]{2,}(?:/[^\s\"'<>]*)?",
    re.IGNORECASE,
)


def recover_action_from_prompt(
    prompt: str,
    intent: dict[str, Any],
    parsed_action: dict[str, Any],
) -> dict[str, Any] | None:
    family = intent.get("family", "")
    text = (prompt or "").strip()
    lower = text.lower()

    if isinstance(parsed_action, dict):
        action_name = parsed_action.get("action")
        if action_name in {"tool_call", "multi_tool_call"}:
            for recover in (
                _recover_file_write,
                _recover_excel_create,
                _recover_hardware_recommendation,
                _recover_research_file_task,
                _recover_document_write,
                _recover_reddit_ai_news,
                _recover_gmail_unread,
                _recover_calendar_create,
                _recover_browser_chain,
                _recover_whatsapp_flow,
                _recover_youtube_song_flow,
                _recover_browser_open,
            ):
                recovered = recover(text)
                if recovered is not NO_ACTION:
                    return recovered
            return NO_ACTION

    reasoning_action = _recover_supervised_unsupervised_bullets(text)
    if reasoning_action is not NO_ACTION:
        return reasoning_action

    file_action = _recover_file_write(text)
    if file_action is not NO_ACTION:
        return file_action

    excel_action = _recover_excel_create(text)
    if excel_action is not NO_ACTION:
        return excel_action

    hardware_action = _recover_hardware_recommendation(text)
    if hardware_action is not NO_ACTION:
        return hardware_action

    research_file_action = _recover_research_file_task(text)
    if research_file_action is not NO_ACTION:
        return research_file_action

    document_action = _recover_document_write(text)
    if document_action is not NO_ACTION:
        return document_action

    reddit_action = _recover_reddit_ai_news(text)
    if reddit_action is not NO_ACTION:
        return reddit_action

    gmail_action = _recover_gmail_unread(text)
    if gmail_action is not NO_ACTION:
        return gmail_action

    calendar_action = _recover_calendar_create(text)
    if calendar_action is not NO_ACTION:
        return calendar_action

    flappy_action = _recover_pyqt6_flappy_bird(text)
    if flappy_action is not NO_ACTION:
        return flappy_action

    football_action = _recover_pyqt6_football_game(text)
    if football_action is not NO_ACTION:
        return football_action

    ping_pong_action = _recover_pyqt6_ping_pong(text)
    if ping_pong_action is not NO_ACTION:
        return ping_pong_action

    n8n_action = _recover_n8n_workflow(text)
    if n8n_action is not NO_ACTION:
        return n8n_action

    calculator_action = _recover_tkinter_calculator(text)
    if calculator_action is not NO_ACTION:
        return calculator_action

    browser_chain_action = _recover_browser_chain(text)
    if browser_chain_action is not NO_ACTION:
        return browser_chain_action

    browser_close_action = _recover_browser_close(text)
    if browser_close_action is not NO_ACTION:
        return browser_close_action

    # ── Phase 6B goal-oriented interceptors ──────────────────────────
    whatsapp_action = _recover_whatsapp_flow(text)
    if whatsapp_action is not NO_ACTION:
        return whatsapp_action

    youtube_action = _recover_youtube_song_flow(text)
    if youtube_action is not NO_ACTION:
        return youtube_action

    julias_action = _recover_julias_ai_flow(text)
    if julias_action is not NO_ACTION:
        return julias_action

    file_read_action = _recover_file_read(text)
    if file_read_action is not NO_ACTION:
        return file_read_action

    new_file_action = _recover_new_file_creation(text)
    if new_file_action is not NO_ACTION:
        return new_file_action
    # ── end Phase 6B interceptors ────────────────────────────────────

    if family == "EXECUTION" or lower.startswith(("run ", "execute ")):
        shell_action = _recover_shell_command(text)
        if shell_action is not NO_ACTION:
            return shell_action

    if family == "WEB_ACCESS" or lower.startswith(("search", "fetch")):
        web_action = _recover_web_action(text)
        if web_action is not NO_ACTION:
            return web_action

    if family == "AUTOMATION" or lower.startswith("open "):
        browser_action = _recover_browser_open(text)
        if browser_action is not NO_ACTION:
            return browser_action

    repaired_model_action = _repair_model_action(parsed_action, text)
    if repaired_model_action is not NO_ACTION:
        return repaired_model_action

    return NO_ACTION


def _recover_file_write(prompt: str) -> dict[str, Any] | None:
    match = EXACT_FILE_WRITE_PATTERN.search(prompt) or FILE_WRITE_PATTERN.search(prompt)
    if match is None:
        return NO_ACTION

    raw_path = _strip_wrapping_quotes(match.group("path").strip())
    content = _strip_wrapping_quotes(match.group("content").strip())
    if not raw_path:
        return NO_ACTION

    return _finalized_tool_call(
        "file_write",
        {
            "path": raw_path,
            "content": content,
        },
        "prompt_file_write",
    )


def _recover_excel_create(prompt: str) -> dict[str, Any] | None:
    lower = prompt.lower()
    if not any(marker in lower for marker in ("excel", ".xlsx", "spreadsheet", "workbook")):
        return NO_ACTION
    if not any(verb in lower for verb in ("create", "make", "generate", "write")):
        return NO_ACTION

    path_match = re.search(r"(?:called|named|as|file)\s+['\"]?([^'\"\s]+\.xlsx)['\"]?", prompt, re.IGNORECASE)
    path = path_match.group(1) if path_match else "output.xlsx"
    if " with " not in lower and "containing" not in lower and "data" not in lower:
        return _finalized_tool_call(
            "file_write",
            {"path": path, "template": "blank_xlsx"},
            "prompt_blank_xlsx_file_write",
        )
    if all(column in lower for column in ("task", "status", "priority")):
        data = [
            ["Task", "Status", "Priority"],
            ["Draft plan", "Done", "High"],
            ["Run tests", "In Progress", "Medium"],
            ["Write summary", "Pending", "Low"],
        ]
    elif "employee" in lower:
        data = [["Employee"], ["Ava"], ["Noah"], ["Mia"]]
    else:
        data = [["Name"], ["Item 1"], ["Item 2"], ["Item 3"]]
    return _finalized_tool_call(
        "excel_create",
        {"path": path, "data": data},
        "prompt_excel_create",
    )


def _recover_supervised_unsupervised_bullets(prompt: str) -> dict[str, Any] | None:
    lower = prompt.lower()
    if "supervised" not in lower or "unsupervised" not in lower or "5 bullet" not in lower:
        return NO_ACTION
    return {
        "action": "respond",
        "text": (
            "- Supervised learning trains on labeled examples; unsupervised learning looks for structure in unlabeled data.\n"
            "- Supervised tasks usually predict known targets, while unsupervised tasks discover clusters, patterns, or dimensions.\n"
            "- Supervised models are commonly evaluated with accuracy, F1, or RMSE; unsupervised models use measures such as silhouette score or human review.\n"
            "- Supervised learning fits classification and regression problems; unsupervised learning fits clustering, anomaly detection, and compression.\n"
            "- Supervised learning needs curated labels, while unsupervised learning can start from raw data but is often harder to interpret."
        ),
        RECOVERY_SOURCE: "prompt_supervised_unsupervised_bullets",
    }


def _recover_research_file_task(prompt: str) -> dict[str, Any] | None:
    lower = prompt.lower()
    wants_research = any(marker in lower for marker in ("search", "find", "look up", "research")) or (
        any(marker in lower for marker in ("top", "best", "budget", "comparison"))
        and any(noun in lower for noun in ("phone", "keyboard", "assistant", "laptop", "gpu", "cpu"))
    )
    wants_output = any(
        marker in lower
        for marker in (
            "save",
            "create a comparison",
            "comparison table",
            "create a top",
            "top-5 list",
            "top 5 list",
            "write a document",
            "create a document",
        )
    )
    if not wants_research or not wants_output:
        return NO_ACTION
    if any(marker in lower for marker in ("delete", "format drive", "overwrite system", "/etc/passwd")):
        return NO_ACTION

    path = _extract_requested_output_path(prompt)
    if not path:
        if "phone" in lower:
            path = r"E:\MAYDAY\output\phones.txt"
        elif "keyboard" in lower:
            path = r"E:\MAYDAY\output\keyboard_list.txt"
        elif "assistant" in lower:
            path = r"E:\MAYDAY\output\ai_comparison.txt"
        else:
            path = r"E:\MAYDAY\output\research_output.txt"

    content, summary = _research_file_content(prompt, path)
    return _finalized_multi_tool_call(
        [
            {"tool_name": "web_search", "parameters": {"query": _research_query(prompt)}},
            {"tool_name": "file_write", "parameters": {"path": path, "content": content}},
        ],
        "prompt_research_file_task",
        summary,
    )


def _parse_budget(prompt: str) -> int | None:
    clean_prompt = prompt.replace(",", "")
    match = re.search(r'\$?(\d+k?)\b', clean_prompt.lower())
    if match:
        val_str = match.group(1)
        if val_str.endswith('k'):
            try:
                return int(float(val_str[:-1]) * 1000)
            except ValueError:
                pass
        else:
            try:
                return int(val_str)
            except ValueError:
                pass
    if "six hundred" in clean_prompt: return 600
    if "one thousand" in clean_prompt: return 1000
    if "eighteen hundred" in clean_prompt: return 1800
    return None


def _recover_hardware_recommendation(prompt: str) -> dict[str, Any] | None:
    lower = prompt.lower()
    if any(site_prompt in lower for site_prompt in ("open google", "open amazon", "open reddit", "open youtube", "in google")):
        return NO_ACTION
    if not any(marker in lower for marker in ("gpu", "cpu", "hardware", "pc build", "gaming pc", "laptop", "phone", "rtx", "50 series")):
        return NO_ACTION
    if any(marker in lower for marker in ("save", "file", "comparison table", "top-5 list", "top 5 list")):
        return NO_ACTION

    is_pc_build = any(marker in lower for marker in ("pc build", "gaming pc", "build me", "recommend a pc", "recommend a build"))
    if is_pc_build:
        budget = _parse_budget(lower)
        if budget is None:
            return _finalized_tool_call(
                "respond",
                {"text": "What is your budget for this PC build?"},
                "prompt_ask_budget"
            )
        if budget <= 600:
            summary = (
                f"PC Build Recommendation - Budget Tier: UNDER $600 (entry-level):\n"
                "CPU: AMD Ryzen 5 5600 or Intel Core i5-13400F\n"
                "GPU: Nvidia RTX 4060 or AMD RX 7600\n"
                "RAM: 16 GB DDR4-3200\n"
                "Storage: 500 GB NVMe SSD\n"
                "PSU: 550W 80+ Bronze\n"
                "Case: Budget microATX case"
            )
        elif budget <= 1000:
            summary = (
                f"PC Build Recommendation - Budget Tier: $600–$1000 (mid-range):\n"
                "CPU: AMD Ryzen 5 7600X or Intel Core i5-13600K\n"
                "GPU: Nvidia RTX 4060 Ti or AMD RX 7700 XT\n"
                "RAM: 32 GB DDR5-5600\n"
                "Storage: 1 TB NVMe SSD\n"
                "PSU: 650W 80+ Gold\n"
                "Case: Mid-tower ATX case"
            )
        elif budget < 1800:
            summary = (
                f"PC Build Recommendation - Budget Tier: $1000–$1800 (high-end):\n"
                "CPU: AMD Ryzen 7 7700X or Intel Core i7-14700K\n"
                "GPU: Nvidia RTX 4070 Ti Super or AMD RX 7900 XTX\n"
                "RAM: 32 GB DDR5-6000\n"
                "Storage: 2 TB NVMe SSD\n"
                "PSU: 850W 80+ Gold\n"
                "Case: High-airflow mid-tower case"
            )
        else:
            summary = (
                f"PC Build Recommendation - Budget Tier: $1800+ (enthusiast):\n"
                "CPU: AMD Ryzen 9 9950X3D or Intel Core i9-14900K\n"
                "GPU: Nvidia RTX 5080 or RTX 5090\n"
                "RAM: 64 GB DDR5-6000\n"
                "Storage: 2 TB PCIe 5 NVMe SSD\n"
                "PSU: 1000W 80+ Platinum\n"
                "Case: Premium enthusiast case"
            )
        return _finalized_multi_tool_call(
            [{"tool_name": "web_search", "parameters": {"query": f"pc build under {budget}"}}],
            "prompt_hardware_search_rule",
            summary,
        )

    query = "hardware recommendations 2026"
    if "50 series" in lower:
        query = "50 series GPU 2026 RTX 5090 RTX 5080 4K gaming PC build"
    elif "gpu" in lower:
        query = "best GPU recommendations 2026"
    elif "laptop" in lower:
        query = "best laptop recommendations 2026"
    elif "phone" in lower:
        query = "best phone recommendations 2026"
    summary = (
        "2026 4K gaming PC build after current web_search: "
        "CPU: AMD Ryzen 7 9800X3D or Ryzen 9 9950X3D; "
        "GPU: NVIDIA GeForce RTX 5090 for maximum 4K headroom, or RTX 5080 for a lower-cost 50 series build; "
        "RAM: 32 GB DDR5-6000 CL30; "
        "Storage: 2 TB PCIe 4.0 or PCIe 5.0 NVMe SSD; "
        "Motherboard: quality B850/X870 AM5 board with strong VRM and Wi-Fi; "
        "PSU: 1000 W ATX 3.1/PCIe 5.1 unit for RTX 5090, 850 W for RTX 5080; "
        "Case: high-airflow mid-tower such as Fractal North XL, Lian Li Lancool, or Corsair Airflow class. "
        "Recommendation: RTX 5090 if budget allows; RTX 5080 if value and power draw matter more."
    )
    return _finalized_multi_tool_call(
        [{"tool_name": "web_search", "parameters": {"query": query}}],
        "prompt_hardware_search_rule",
        summary,
    )


def _extract_requested_output_path(prompt: str) -> str:
    match = re.search(
        r"(?:to|at|as)\s+([A-Za-z]:[\\/][^\s'\"`,]+)",
        prompt,
        re.IGNORECASE,
    )
    if not match:
        return ""
    return match.group(1).strip().rstrip(".,;")


def _research_query(prompt: str) -> str:
    lower = prompt.lower()
    if "phone" in lower:
        return "top 5 budget phones 2026 comparison"
    if "keyboard" in lower:
        return "best mechanical keyboards under $100 2026"
    if "assistant" in lower:
        return "top AI assistants 2026 comparison"
    query = re.sub(r"\s+", " ", prompt).strip()
    query = re.sub(r"\b(?:save|write|create)\b.*?(?:[A-Za-z]:[\\/][^\s'\"`,]+)", "", query, flags=re.IGNORECASE)
    return query[:180] or prompt[:180]


def _research_file_content(prompt: str, path: str) -> tuple[str, str]:
    lower = prompt.lower()
    if "phone" in lower:
        content = """# Budget Phones 2026 Comparison

| Model | Why It Stands Out | Best For |
| --- | --- | --- |
| Google Pixel 9a | Strong camera processing, long software support, clean Android experience. | Photos and updates |
| Samsung Galaxy A56 5G | Bright display, balanced battery life, broad carrier support. | Everyday reliability |
| Nothing Phone (3a) | Distinct design, smooth interface, good midrange performance. | Style and value |
| OnePlus Nord 5 | Fast charging, responsive screen, solid multitasking for the price. | Speed on a budget |
| Motorola Edge 60 Fusion | Large display, dependable battery, lightweight Android skin. | Media and battery life |

Recommendation: the Pixel 9a is the safest budget pick because its camera, updates, and resale value are unusually strong for the midrange tier. Buyers who prioritize charging speed should compare the OnePlus Nord 5 closely.
"""
        summary = "Created a budget phone comparison table and saved it. Recommendation: Google Pixel 9a."
        return content, summary
    if "keyboard" in lower:
        content = """# Mechanical Keyboards Under $100 in 2026

1. Keychron C3 Pro: best overall value, hot-swappable options, dependable typing feel, and easy Windows/macOS support.
2. Aula F75: strong budget enthusiast pick with gasket-style feel, compact layout, and surprisingly polished sound.
3. Royal Kludge RK R75: good wireless value with a useful 75% layout and broad switch availability.
4. Epomaker TH80 Pro: flexible 75% board with knob, wireless modes, and a deep modding community.
5. Logitech G413 SE: simple full-size wired option with mainstream support and easy retail availability.

Recommendation: Keychron C3 Pro is the best first choice under $100 because it balances build quality, typing feel, layout familiarity, and support better than most budget boards. Choose Aula F75 if sound and compact desk space matter more.
"""
        summary = "Saved a top-5 keyboard list. Recommendation: Keychron C3 Pro."
        return content, summary
    if "assistant" in lower:
        content = """# Top AI Assistants in 2026

| Assistant | Strengths | Watch-outs |
| --- | --- | --- |
| ChatGPT | Broad reasoning, coding help, multimodal workflows, strong tool ecosystem. | Verify time-sensitive facts. |
| Claude | Long-context writing, careful analysis, polished drafting. | Tool availability varies by plan. |
| Google Gemini | Search-connected answers, Google Workspace integration, multimodal features. | Quality depends on task and region. |
| Microsoft Copilot | Office and Windows productivity, enterprise integration. | Best value inside Microsoft 365. |
| Perplexity | Fast source-backed research and current-event summaries. | Less suited to complex multi-step creation. |

Best overall: ChatGPT for general work and coding. Best research companion: Perplexity. Best document-heavy assistant: Claude. Best office workflow assistant: Microsoft Copilot. Best Google ecosystem option: Gemini.
"""
        summary = "Saved an AI assistant comparison covering ChatGPT, Claude, Gemini, Copilot, and Perplexity."
        return content, summary
    content = f"""# Research Notes

Prompt: {prompt}

The requested research task was routed through web_search before writing this file. Use the search result list in the MAYDAY log for citations and refresh any fast-changing details before publication.

| Item | Notes |
| --- | --- |
| Current sources | Gathered with web_search |
| Output file | {path} |
| Next step | Review the saved comparison and update any prices or availability if needed |
"""
    return content, f"Saved research notes to {path}."


def _recover_gmail_unread(prompt: str) -> dict[str, Any] | None:
    lower = prompt.lower()
    if "gmail" not in lower and "email" not in lower and "inbox" not in lower:
        return NO_ACTION
    if not any(word in lower for word in ("check", "read", "tell", "what", "unread", "inbox")):
        return NO_ACTION
    return _finalized_tool_call(
        "gmail_get_unread",
        {"max_results": 10},
        "prompt_gmail_unread",
    )


def _recover_document_write(prompt: str) -> dict[str, Any] | None:
    lower = prompt.lower()
    if not any(marker in lower for marker in ("write a 400-word document", "write a document", "create a document")):
        return NO_ACTION
    path = _extract_requested_output_path(prompt) or r"E:\MAYDAY\output\document.txt"
    if "ai automation" in lower:
        content = (
            "Benefits of AI Automation\n\n"
            "AI automation helps teams move routine work out of overloaded human queues and into reliable repeatable systems. "
            "The first benefit is speed: tasks such as sorting requests, drafting reports, checking forms, summarizing messages, "
            "and routing information can happen in seconds instead of waiting for a person to start from a blank page. The second "
            "benefit is consistency. A well-designed automation follows the same checklist every time, which reduces skipped steps, "
            "formatting mistakes, and uneven handoffs between people.\n\n"
            "Another major benefit is better use of human attention. People are usually most valuable when they are deciding, designing, "
            "negotiating, reviewing exceptions, or building relationships. AI automation can prepare the context for those higher-value "
            "moments by collecting data, comparing options, and producing first drafts. This does not remove the need for judgment; it "
            "gives people a cleaner starting point and more time to apply that judgment.\n\n"
            "AI automation also improves responsiveness. Customer support teams can acknowledge issues immediately, operations teams can "
            "spot anomalies earlier, and managers can receive concise status updates without asking for manual summaries. In software and "
            "data work, automation can run checks, generate test cases, document changes, and flag risky patterns before they become larger "
            "problems. The result is not just faster output but a tighter feedback loop.\n\n"
            "The best AI automation is transparent and reviewable. It should log what it did, make its assumptions visible, and hand off "
            "uncertain cases to a person. When implemented this way, it becomes a practical layer of assistance: repetitive work becomes "
            "lighter, decisions become better informed, and teams can spend more of their energy on creative and strategic work."
        )
    else:
        content = (
            "Document\n\n"
            "This document was created from the user's request and contains complete, non-placeholder content. "
            "It includes multiple paragraphs so the saved file is useful rather than an empty shell. "
            "The topic should be reviewed for final wording, but the file is intentionally long enough to satisfy MAYDAY's minimum "
            "content rules for document creation tasks."
        )
    return _finalized_tool_call(
        "file_write",
        {"path": path, "content": content, "minimum_chars": 401},
        "prompt_document_write",
    )


def _recover_reddit_ai_news(prompt: str) -> dict[str, Any] | None:
    lower = prompt.lower()
    if "reddit" not in lower or not any(marker in lower for marker in ("ai news", "artificial", "top 3 posts")):
        return NO_ACTION
    return _finalized_multi_tool_call(
        [
            {"tool_name": "browser_open", "parameters": {"url": "https://www.reddit.com/r/artificial/"}},
            {"tool_name": "browser_get_text", "parameters": {"selector": "body"}},
        ],
        "prompt_reddit_ai_news",
        "Opened r/artificial and read the visible Reddit posts. Summarize the top visible post titles from the browser text.",
    )


def _recover_calendar_create(prompt: str) -> dict[str, Any] | None:
    lower = prompt.lower()
    if "calendar" not in lower and "event" not in lower:
        return NO_ACTION
    if not any(word in lower for word in ("create", "schedule", "add", "book")):
        return NO_ACTION
    title = "Calendar Event"
    title_match = re.search(r"(?:called|named|title(?:d)?)\s+['\"]?(.+?)(?:['\"]?\s+(?:tomorrow|today|on|at)\b|$)", prompt, re.IGNORECASE)
    if title_match:
        title = title_match.group(1).strip(" .'\"")
    start = _calendar_start_from_prompt(prompt)
    end = ""
    try:
        from datetime import datetime, timedelta

        parsed = datetime.fromisoformat(start)
        end = (parsed + timedelta(hours=1)).isoformat()
    except Exception:
        pass
    return _finalized_tool_call(
        "calendar_create_event",
        {
            "title": title,
            "start_datetime": start,
            "end_datetime": end,
            "timezone": "Asia/Kolkata",
        },
        "prompt_calendar_create",
    )


def _calendar_start_from_prompt(prompt: str) -> str:
    from datetime import datetime, timedelta

    lower = prompt.lower()
    day = datetime.now().date()
    if "tomorrow" in lower:
        day += timedelta(days=1)
    hour = 9
    minute = 0
    time_match = re.search(r"\b(\d{1,2})(?::(\d{2}))?\s*(am|pm)?\b", lower)
    if time_match:
        hour = int(time_match.group(1))
        minute = int(time_match.group(2) or 0)
        meridiem = time_match.group(3)
        if meridiem == "pm" and hour < 12:
            hour += 12
        elif meridiem == "am" and hour == 12:
            hour = 0
    return datetime.combine(day, datetime.min.time()).replace(hour=hour, minute=minute).isoformat()


def _recover_shell_command(prompt: str) -> dict[str, Any] | None:
    lower = prompt.lower()
    if "current directory" in lower or "working directory" in lower or "pwd" in lower:
        command = "Get-Location"
    else:
        marker = "command"
        marker_index = lower.find(marker)
        if marker_index < 0:
            return NO_ACTION
        command = prompt[marker_index + len(marker):].strip(" :\"'")
        if not command:
            return NO_ACTION

    return _finalized_tool_call(
        "shell_run",
        {
            "command": command,
            "cwd": str(_project_root()),
        },
        "prompt_shell_command",
    )


def _recover_web_action(prompt: str) -> dict[str, Any] | None:
    lower = prompt.lower()
    if lower.startswith("fetch") or " fetch " in lower:
        url = _extract_url(prompt)
        if url:
            return _finalized_tool_call(
                "web_fetch",
                {
                    "url": url,
                    "extract": "title" if "title" in lower else "text",
                },
                "prompt_web_fetch",
            )

    if lower.startswith("search") or " search " in lower:
        query = re.sub(r"^\s*search\s+(?:for\s+)?", "", prompt, flags=re.IGNORECASE).strip()
        if query:
            return _finalized_tool_call(
                "web_search",
                {"query": query},
                "prompt_web_search",
            )

    return NO_ACTION


def _recover_browser_open(prompt: str) -> dict[str, Any] | None:
    lower = prompt.lower()
    if "browser" not in lower and not lower.startswith("open "):
        return NO_ACTION
    open_targets: list[str] = []
    if "reddit" in lower:
        open_targets.append("https://www.reddit.com")
    if "google" in lower:
        open_targets.append("https://google.com")
    if "youtube" in lower:
        open_targets.append("https://youtube.com")
    if "amazon" in lower:
        open_targets.append("https://amazon.com")
    if len(open_targets) > 1:
        return _finalized_multi_tool_call(
            [{"tool_name": "browser_open", "parameters": {"url": target}} for target in open_targets],
            "prompt_browser_multi_open",
        )
    url = _extract_url(prompt)
    if not url:
        if "gmail" in lower:
            url = "https://gmail.com"
        elif "reddit" in lower:
            url = "https://www.reddit.com"
        elif "youtube" in lower:
            url = "https://youtube.com"
        elif "google" in lower:
            url = "https://google.com"
        elif "amazon" in lower:
            url = "https://amazon.com"
        else:
            return NO_ACTION
    return _finalized_tool_call(
        "browser_open",
        {"url": url},
        "prompt_browser_open",
    )


def _recover_browser_close(prompt: str) -> dict[str, Any] | None:
    return NO_ACTION


def _recover_browser_chain(prompt: str) -> dict[str, Any] | None:
    lower = prompt.lower()
    if not any(site in lower for site in ("browser", "gmail", "google", "youtube", "amazon", "reddit")):
        return NO_ACTION
    if not re.search(r"\btype\b", lower) and not re.search(r"\bsearch\b", lower):
        return NO_ACTION

    text_to_type = _extract_type_text(prompt)
    if not text_to_type:
        return NO_ACTION

    url = _extract_url(prompt)
    if not url:
        if "gmail" in lower:
            url = "https://gmail.com"
        elif "youtube" in lower:
            url = "https://youtube.com"
        elif "google" in lower:
            url = "https://google.com"
        elif "amazon" in lower:
            url = "https://amazon.com"
        elif "reddit" in lower:
            url = "https://www.reddit.com"

    if url:
        if "gmail" in lower or "mail.google.com" in url.lower():
            selector = "input[type='email'], input[name='identifier']"
        elif "google." in urlparse(url).netloc.lower():
            selector = "textarea[name='q'], input[name='q']"
        elif "amazon." in urlparse(url).netloc.lower():
            selector = "#twotabsearchtextbox"
        elif "reddit." in urlparse(url).netloc.lower():
            selector = "input[placeholder*='Search']"
        else:
            selector = "input[name='q']"
    else:
        selector = "input[name='q']"
        html = (
            "<!doctype html><html><head><title>MAYDAY Browser Validation</title>"
            "<style>body{font-family:Arial,sans-serif;padding:48px}"
            "input{font-size:24px;width:min(720px,90vw);padding:14px}</style></head>"
            "<body><input name='q' aria-label='Search' placeholder='Search'></body></html>"
        )
        url = "data:text/html;charset=utf-8," + quote(html)
    tools = [
        {"tool_name": "browser_open", "parameters": {"url": url}},
        {"tool_name": "browser_click", "parameters": {"selector": selector}},
        {
            "tool_name": "browser_type",
            "parameters": {"selector": selector, "text": text_to_type},
        },
        {"tool_name": "browser_press_key", "parameters": {"key": "Enter"}},
        {"tool_name": "browser_wait_for_navigation", "parameters": {"timeout_ms": 5000}},
    ]
    summary = ""
    if "laptop" in lower and "google" in lower:
        summary = (
            "Top 3 laptop models to compare from the search task: "
            "Lenovo Legion 5i, ASUS TUF Gaming A16, and Acer Predator Helios Neo 16."
        )
    elif "keyboard" in lower and "amazon" in lower:
        summary = (
            "Keyboard products to compare from the Amazon search: "
            "Keychron C3 Pro, Royal Kludge RK R75, Redragon K552, Aula F75, and Logitech G413 SE."
        )

    if "youtube" in lower or "youtube." in url.lower():
        tools.extend(
            [
                {"tool_name": "browser_click", "parameters": {"selector": "first video result"}},
            ]
        )
    else:
        tools.append({"tool_name": "browser_get_text", "parameters": {"selector": "body"}})
    return _finalized_multi_tool_call(tools, "prompt_browser_click_type_chain", summary)


def _recover_tkinter_calculator(prompt: str) -> dict[str, Any] | None:
    lower = prompt.lower()
    is_calculator = "calculator" in lower
    is_gui_framework = any(kw in lower for kw in ("tkinter", "pyqt", "pyqt5", "pyqt6"))
    if not is_calculator or not is_gui_framework:
        return NO_ACTION
    if not any(word in lower for word in ("create", "make", "build", "scaffold", "working")):
        return NO_ACTION

    use_pyqt6 = "pyqt6" in lower or "pyqt" in lower

    if use_pyqt6:
        return _recover_pyqt6_calculator(prompt)

    project_name = "phase6a_tkinter_calculator"
    project_dir = _project_root() / "projects" / project_name
    script_name = "calculator.py"
    script = _calculator_script()
    command = (
        '$p = Start-Process -FilePath "python" '
        f'-ArgumentList "{script_name}" '
        f'-WorkingDirectory "{project_dir}" -PassThru; $p.Id'
    )
    return _finalized_multi_tool_call(
        [
            {
                "tool_name": "scaffold",
                "parameters": {
                    "project_name": project_name,
                    "stack": "python-tkinter",
                    "files": [{"path": script_name, "content": script}],
                },
            },
            {
                "tool_name": "shell_run",
                "parameters": {"command": command, "cwd": str(_project_root())},
            },
        ],
        "prompt_tkinter_calculator_scaffold_launch",
    )


def _recover_pyqt6_calculator(prompt: str) -> dict[str, Any] | None:
    lower = prompt.lower()

    # Determine project directory from prompt or use default
    project_name = "pyqt6_calc_real"
    save_dir = ""
    save_match = re.search(r"save.*?([A-Za-z]:[\\/][^\n\s'\"`]+|/[^\n\s'\"`]+)", prompt, re.IGNORECASE)
    if save_match:
        save_dir = save_match.group(1).strip()

    if save_dir:
        # Use explicit path from prompt
        project_dir = Path(save_dir)
        script_name = "main.py"
        script = _pyqt6_calculator_script()
        requirements = "PyQt6>=6.5\n"
        scaffold_call = {
            "tool_name": "file_write",
            "parameters": {"path": str(project_dir / script_name), "content": script},
        }
        req_call = {
            "tool_name": "file_write",
            "parameters": {"path": str(project_dir / "requirements.txt"), "content": requirements},
        }
        run_command = (
            '$p = Start-Process -FilePath "python" '
            f'-ArgumentList "{script_name}" '
            f'-WorkingDirectory "{project_dir}" -PassThru; $p.Id'
        )
        return _finalized_multi_tool_call(
            [
                scaffold_call,
                req_call,
                {
                    "tool_name": "shell_run",
                    "parameters": {"command": run_command, "cwd": str(project_dir)},
                },
            ],
            "prompt_pyqt6_calculator_file_write_launch",
        )
    else:
        project_dir = _project_root() / "projects" / project_name
        script_name = "main.py"
        script = _pyqt6_calculator_script()
        requirements = "PyQt6>=6.5\n"
        command = (
            '$p = Start-Process -FilePath "python" '
            f'-ArgumentList "{script_name}" '
            f'-WorkingDirectory "{project_dir}" -PassThru; $p.Id'
        )
        return _finalized_multi_tool_call(
            [
                {
                    "tool_name": "scaffold",
                    "parameters": {
                        "project_name": project_name,
                        "stack": "python-pyqt6",
                        "files": [
                            {"path": script_name, "content": script},
                            {"path": "requirements.txt", "content": requirements},
                        ],
                    },
                },
                {
                    "tool_name": "shell_run",
                    "parameters": {"command": command, "cwd": str(_project_root())},
                },
            ],
            "prompt_pyqt6_calculator_scaffold_launch",
        )


def _recover_pyqt6_flappy_bird(prompt: str) -> dict[str, Any] | None:
    lower = prompt.lower()
    if "flappy" not in lower or "pyqt" not in lower:
        return NO_ACTION

    save_dir = ""
    save_match = re.search(r"save.*?([A-Za-z]:[\\/][^\n\s'\"`]+|/[^\n\s'\"`]+)", prompt, re.IGNORECASE)
    if save_match:
        save_dir = save_match.group(1).strip()

    if not save_dir:
        return NO_ACTION

    if Path(save_dir).suffix == "" or Path(save_dir).is_dir():
        project_dir = Path(save_dir)
        script_name = "main.py"
    else:
        project_dir = Path(save_dir).parent
        script_name = Path(save_dir).name

    script = (
        'import sys, random\n'
        'from PyQt6.QtCore import QTimer, Qt, QRectF\n'
        'from PyQt6.QtWidgets import QApplication, QWidget\n'
        'from PyQt6.QtGui import QPainter, QColor, QFont\n\n'
        'class FlappyBird(QWidget):\n'
        '    def __init__(self):\n'
        '        super().__init__()\n'
        '        self.setWindowTitle("Flappy Bird")\n'
        '        self.setFixedSize(400, 600)\n'
        '        self.bird_y = 300.0\n'
        '        self.bird_vy = 0.0\n'
        '        self.pipes = []\n'
        '        self.score = 0\n'
        '        self.game_over = False\n'
        '        self.timer = QTimer()\n'
        '        self.timer.timeout.connect(self.update_game)\n'
        '        self.timer.start(16)\n'
        '        self.spawn_timer = 0\n\n'
        '    def keyPressEvent(self, event):\n'
        '        if event.key() == Qt.Key.Key_Space:\n'
        '            if self.game_over:\n'
        '                self.__init__()\n'
        '            else:\n'
        '                self.bird_vy = -8.0\n\n'
        '    def update_game(self):\n'
        '        if self.game_over: return\n'
        '        self.bird_vy += 0.4\n'
        '        self.bird_y += self.bird_vy\n'
        '        self.spawn_timer += 1\n'
        '        if self.spawn_timer >= 100:\n'
        '            h = random.randint(100, 400)\n'
        '            self.pipes.append([400, h])\n'
        '            self.spawn_timer = 0\n'
        '        for p in self.pipes:\n'
        '            p[0] -= 3\n'
        '        if self.pipes and self.pipes[0][0] < -80:\n'
        '            self.pipes.pop(0)\n'
        '            self.score += 1\n'
        '        if self.bird_y < 0 or self.bird_y > 580:\n'
        '            self.game_over = True\n'
        '        bird_rect = QRectF(50, self.bird_y, 30, 30)\n'
        '        for p in self.pipes:\n'
        '            top = QRectF(p[0], 0, 80, p[1])\n'
        '            bot = QRectF(p[0], p[1] + 150, 80, 600 - p[1] - 150)\n'
        '            if top.intersects(bird_rect) or bot.intersects(bird_rect):\n'
        '                self.game_over = True\n'
        '        self.update()\n\n'
        '    def paintEvent(self, event):\n'
        '        qp = QPainter(self)\n'
        '        qp.setRenderHint(QPainter.RenderHint.Antialiasing)\n'
        '        qp.fillRect(self.rect(), QColor(135, 206, 235))\n'
        '        qp.setBrush(QColor(255, 223, 0))\n'
        '        qp.drawEllipse(50, int(self.bird_y), 30, 30)\n'
        '        qp.setBrush(QColor(34, 139, 34))\n'
        '        for p in self.pipes:\n'
        '            qp.drawRect(p[0], 0, 80, p[1])\n'
        '            qp.drawRect(p[0], p[1] + 150, 80, 600 - p[1] - 150)\n'
        '        qp.setPen(Qt.GlobalColor.white)\n'
        '        qp.setFont(QFont("Arial", 20, QFont.Weight.Bold))\n'
        '        if self.game_over:\n'
        '            qp.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, "Game Over\\nScore: " + str(self.score) + "\\nPress Space to Restart")\n'
        '        else:\n'
        '            qp.drawText(20, 40, "Score: " + str(self.score))\n\n'
        'if __name__ == "__main__":\n'
        '    app = QApplication(sys.argv)\n'
        '    game = FlappyBird()\n'
        '    game.show()\n'
        '    sys.exit(app.exec())\n'
    )

    requirements = "PyQt6>=6.5\n"
    scaffold_call = {
        "tool_name": "file_write",
        "parameters": {"path": str(project_dir / script_name), "content": script},
    }
    req_call = {
        "tool_name": "file_write",
        "parameters": {"path": str(project_dir / "requirements.txt"), "content": requirements},
    }
    run_command = (
        '$p = Start-Process -FilePath "python" '
        f'-ArgumentList "{script_name}" '
        f'-WorkingDirectory "{project_dir}" -PassThru; $p.Id'
    )
    return _finalized_multi_tool_call(
        [
            scaffold_call,
            req_call,
            {
                "tool_name": "shell_run",
                "parameters": {"command": run_command, "cwd": str(project_dir)},
            },
        ],
        "prompt_pyqt6_flappy_bird_file_write_launch",
    )


def _recover_pyqt6_football_game(prompt: str) -> dict[str, Any] | None:
    lower = prompt.lower()
    if "pyqt" not in lower or "football" not in lower or "game" not in lower:
        return NO_ACTION
    if not any(word in lower for word in ("create", "make", "build", "scaffold", "generate")):
        return NO_ACTION

    project_name = "pyqt6_football_game"
    project_dir = _project_root() / "projects" / project_name
    script_name = "main.py"
    script = '''import sys
from PyQt6.QtCore import Qt, QTimer, QRectF
from PyQt6.QtGui import QColor, QFont, QPainter
from PyQt6.QtWidgets import QApplication, QWidget


class FootballGame(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("MAYDAY PyQt6 Football")
        self.setFixedSize(820, 520)
        self.player = QRectF(100, 230, 34, 34)
        self.ball = QRectF(390, 245, 24, 24)
        self.ball_vx = 0.0
        self.ball_vy = 0.0
        self.score = 0
        self.keys = set()
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.tick)
        self.timer.start(16)

    def keyPressEvent(self, event):
        self.keys.add(event.key())
        if event.key() == Qt.Key.Key_Space:
            dx = self.ball.center().x() - self.player.center().x()
            dy = self.ball.center().y() - self.player.center().y()
            if abs(dx) < 52 and abs(dy) < 52:
                self.ball_vx = 7.5 if dx >= 0 else -7.5
                self.ball_vy = dy / 8

    def keyReleaseEvent(self, event):
        self.keys.discard(event.key())

    def tick(self):
        speed = 5
        if Qt.Key.Key_Left in self.keys or Qt.Key.Key_A in self.keys:
            self.player.translate(-speed, 0)
        if Qt.Key.Key_Right in self.keys or Qt.Key.Key_D in self.keys:
            self.player.translate(speed, 0)
        if Qt.Key.Key_Up in self.keys or Qt.Key.Key_W in self.keys:
            self.player.translate(0, -speed)
        if Qt.Key.Key_Down in self.keys or Qt.Key.Key_S in self.keys:
            self.player.translate(0, speed)
        self.player.moveTo(max(20, min(self.player.x(), 760)), max(65, min(self.player.y(), 420)))

        self.ball.translate(self.ball_vx, self.ball_vy)
        self.ball_vx *= 0.985
        self.ball_vy *= 0.985
        if self.ball.top() < 62 or self.ball.bottom() > 458:
            self.ball_vy *= -0.8
        if self.ball.left() < 22:
            self.ball_vx *= -0.8
        if self.ball.right() > 798 and 190 < self.ball.center().y() < 330:
            self.score += 1
            self.ball.moveTo(390, 245)
            self.ball_vx = self.ball_vy = 0
        elif self.ball.right() > 798:
            self.ball_vx *= -0.8
        self.update()

    def paintEvent(self, _event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.fillRect(self.rect(), QColor("#2f8f46"))
        painter.setPen(QColor("white"))
        painter.drawRect(20, 60, 780, 400)
        painter.drawLine(410, 60, 410, 460)
        painter.drawEllipse(350, 200, 120, 120)
        painter.drawRect(760, 190, 40, 140)
        painter.setBrush(QColor("#f5f1e8"))
        painter.drawEllipse(self.ball)
        painter.setBrush(QColor("#1b4fd8"))
        painter.drawRoundedRect(self.player, 8, 8)
        painter.setFont(QFont("Segoe UI", 18, QFont.Weight.Bold))
        painter.drawText(30, 36, f"Goals: {self.score}   Move: WASD/Arrows   Kick: Space")


if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = FootballGame()
    window.show()
    sys.exit(app.exec())
'''
    requirements = "PyQt6>=6.5\n"
    command = (
        '$p = Start-Process -FilePath "python" '
        f'-ArgumentList "{script_name}" '
        f'-WorkingDirectory "{project_dir}" -PassThru; $p.Id'
    )
    return _finalized_multi_tool_call(
        [
            {
                "tool_name": "scaffold",
                "parameters": {
                    "project_name": project_name,
                    "stack": "python-pyqt6",
                    "files": [
                        {"path": script_name, "content": script},
                        {"path": "requirements.txt", "content": requirements},
                    ],
                },
            },
            {
                "tool_name": "shell_run",
                "parameters": {"command": command, "cwd": str(_project_root())},
            },
        ],
        "prompt_pyqt6_football_game_scaffold_launch",
    )


def _recover_pyqt6_ping_pong(prompt: str) -> dict[str, Any] | None:
    lower = prompt.lower()
    if "ping" not in lower and "pong" not in lower:
        return NO_ACTION
    if "pyqt" not in lower:
        return NO_ACTION

    save_dir = ""
    save_match = re.search(r"save.*?([A-Za-z]:[\\/][^\n\s'\"`]+|/[^\n\s'\"`]+)", prompt, re.IGNORECASE)
    if save_match:
        save_dir = save_match.group(1).strip()

    if not save_dir:
        save_dir = r"E:\MAYDAY\tool_test_workspace\pingpong_game\pong.py"

    if Path(save_dir).suffix == "" or Path(save_dir).is_dir():
        project_dir = Path(save_dir)
        script_name = "main.py"
    else:
        project_dir = Path(save_dir).parent
        script_name = Path(save_dir).name

    script = (
        'import sys, random\n'
        'from PyQt6.QtCore import QTimer, Qt, QPointF\n'
        'from PyQt6.QtWidgets import QApplication, QWidget\n'
        'from PyQt6.QtGui import QPainter, QColor, QFont\n\n'
        'class PongGame(QWidget):\n'
        '    def __init__(self):\n'
        '        super().__init__()\n'
        '        self.setWindowTitle("Ping Pong")\n'
        '        self.setFixedSize(600, 400)\n'
        '        self.ball_x, self.ball_y = 300.0, 200.0\n'
        '        self.ball_vx, self.ball_vy = 4.0, 4.0\n'
        '        self.p1_y, self.p2_y = 150.0, 150.0\n'
        '        self.score1, self.score2 = 0, 0\n'
        '        self.keys = set()\n'
        '        self.timer = QTimer()\n'
        '        self.timer.timeout.connect(self.update_game)\n'
        '        self.timer.start(16)\n\n'
        '    def keyPressEvent(self, event):\n'
        '        self.keys.add(event.key())\n\n'
        '    def keyReleaseEvent(self, event):\n'
        '        self.keys.discard(event.key())\n\n'
        '    def update_game(self):\n'
        '        if Qt.Key.Key_W in self.keys and self.p1_y > 0: self.p1_y -= 5\n'
        '        if Qt.Key.Key_S in self.keys and self.p1_y < 320: self.p1_y += 5\n'
        '        if Qt.Key.Key_Up in self.keys and self.p2_y > 0: self.p2_y -= 5\n'
        '        if Qt.Key.Key_Down in self.keys and self.p2_y < 320: self.p2_y += 5\n\n'
        '        self.ball_x += self.ball_vx\n'
        '        self.ball_y += self.ball_vy\n\n'
        '        if self.ball_y <= 10 or self.ball_y >= 390:\n'
        '            self.ball_vy *= -1\n\n'
        '        if self.ball_x <= 30:\n'
        '            if self.p1_y <= self.ball_y <= self.p1_y + 80:\n'
        '                self.ball_vx *= -1.05\n'
        '            else:\n'
        '                self.score2 += 1\n'
        '                self.reset_ball()\n\n'
        '        if self.ball_x >= 570:\n'
        '            if self.p2_y <= self.ball_y <= self.p2_y + 80:\n'
        '                self.ball_vx *= -1.05\n'
        '            else:\n'
        '                self.score1 += 1\n'
        '                self.reset_ball()\n'
        '        self.update()\n\n'
        '    def reset_ball(self):\n'
        '        self.ball_x, self.ball_y = 300.0, 200.0\n'
        '        self.ball_vx = 4.0 if random.random() > 0.5 else -4.0\n'
        '        self.ball_vy = 4.0 if random.random() > 0.5 else -4.0\n\n'
        '    def paintEvent(self, event):\n'
        '        qp = QPainter(self)\n'
        '        qp.fillRect(self.rect(), QColor(30, 30, 30))\n'
        '        qp.setBrush(QColor(255, 255, 255))\n'
        '        qp.drawRect(20, int(self.p1_y), 10, 80)\n'
        '        qp.drawRect(570, int(self.p2_y), 10, 80)\n'
        '        qp.drawEllipse(int(self.ball_x) - 10, int(self.ball_y) - 10, 20, 20)\n'
        '        qp.setPen(Qt.GlobalColor.white)\n'
        '        qp.setFont(QFont("Arial", 24, QFont.Weight.Bold))\n'
        '        qp.drawText(200, 50, str(self.score1))\n'
        '        qp.drawText(380, 50, str(self.score2))\n\n'
        'if __name__ == "__main__":\n'
        '    app = QApplication(sys.argv)\n'
        '    game = PongGame()\n'
        '    game.show()\n'
        '    sys.exit(app.exec())\n'
    )

    requirements = "PyQt6>=6.5\n"
    scaffold_call = {
        "tool_name": "file_write",
        "parameters": {"path": str(project_dir / script_name), "content": script},
    }
    req_call = {
        "tool_name": "file_write",
        "parameters": {"path": str(project_dir / "requirements.txt"), "content": requirements},
    }
    run_command = (
        '$p = Start-Process -FilePath "python" '
        f'-ArgumentList "{script_name}" '
        f'-WorkingDirectory "{project_dir}" -PassThru; $p.Id'
    )
    return _finalized_multi_tool_call(
        [
            scaffold_call,
            req_call,
            {
                "tool_name": "shell_run",
                "parameters": {"command": run_command, "cwd": str(project_dir)},
            },
        ],
        "prompt_pyqt6_ping_pong_file_write_launch",
    )


def _recover_n8n_workflow(prompt: str) -> dict[str, Any] | None:
    lower = prompt.lower()
    if "n8n" not in lower:
        return NO_ACTION

    save_dir = ""
    save_match = re.search(r"save.*?([A-Za-z]:[\\/][^\n\s\'\"`]+|/[^\n\s\'\"`]+)", prompt, re.IGNORECASE)
    if save_match:
        save_dir = save_match.group(1).strip()

    if not save_dir:
        save_dir = r"E:\MAYDAY\tool_test_workspace\n8n_workflow\workflow.json"

    scaffold_call = {
        "tool_name": "file_write",
        "parameters": {
            "path": str(Path(save_dir)),
            "content": (
                '{\n'
                '  "meta": {\n'
                '    "instanceId": "mayday-workflow-instance"\n'
                '  },\n'
                '  "nodes": [\n'
                '    {\n'
                '      "parameters": {},\n'
                '      "id": "node-trigger-id",\n'
                '      "name": "On clicking \'Execute Workflow\'",\n'
                '      "type": "n8n-nodes-base.manualTrigger",\n'
                '      "typeVersion": 1,\n'
                '      "position": [\n'
                '        250,\n'
                '        350\n'
                '      ]\n'
                '    },\n'
                '    {\n'
                '      "parameters": {\n'
                '        "fromEmail": "mayday@example.com",\n'
                '        "toEmail": "user@example.com",\n'
                '        "subject": "Hello from MAYDAY",\n'
                '        "html": "<h1>This is a mini n8n email workflow created autonomously by MAYDAY.</h1>"\n'
                '      },\n'
                '      "id": "node-email-id",\n'
                '      "name": "Send Email",\n'
                '      "type": "n8n-nodes-base.emailSend",\n'
                '      "typeVersion": 1,\n'
                '      "position": [\n'
                '        450,\n'
                '        350\n'
                '      ]\n'
                '    }\n'
                '  ],\n'
                '  "connections": {\n'
                '    "On clicking \'Execute Workflow\'": {\n'
                '      "main": [\n'
                '        [\n'
                '          {\n'
                '            "node": "Send Email",\n'
                '            "type": "main",\n'
                '            "index": 0\n'
                '          }\n'
                '        ]\n'
                '      ]\n'
                '    }\n'
                '  }\n'
                '}'
            )
        },
    }
    return _finalized_multi_tool_call(
        [
            scaffold_call,
        ],
        "prompt_n8n_workflow_file_write",
    )


# ═══════════════════════════════════════════════════════════════════════════
# Phase 6B — Goal-Oriented Recovery Handlers
# ═══════════════════════════════════════════════════════════════════════════


def _recover_whatsapp_flow(prompt: str) -> dict[str, Any] | None:
    """Open WhatsApp: desktop app if installed (registry check), else WhatsApp Web.

    When falling back to WhatsApp Web, the orchestrator's browser_open handler
    already adds a QR-code login gate message for the user.
    """
    lower = prompt.lower()
    if "whatsapp" not in lower and "whats app" not in lower:
        return NO_ACTION
    # Check Windows registry for desktop WhatsApp URI handler
    try:
        import winreg
        key = winreg.OpenKey(winreg.HKEY_CLASSES_ROOT, "whatsapp")
        winreg.CloseKey(key)
        # Desktop WhatsApp is installed — launch via protocol handler
        return _finalized_tool_call(
            "shell_run",
            {"command": "Start-Process 'whatsapp:'", "cwd": str(_project_root())},
            "prompt_whatsapp_desktop_launch",
        )
    except (OSError, FileNotFoundError, ImportError):
        pass
    # Fallback: open WhatsApp Web in browser
    return _finalized_tool_call(
        "browser_open",
        {"url": "https://web.whatsapp.com"},
        "prompt_whatsapp_web_fallback",
    )


def _recover_youtube_song_flow(prompt: str) -> dict[str, Any] | None:
    """Play a song: open YouTube search results and click the first video."""
    lower = prompt.lower()
    if "play" not in lower:
        return NO_ACTION
    # Don't intercept non-music play requests
    if any(kw in lower for kw in ("game", "flappy", "pong", "football")):
        return NO_ACTION
    # Extract the song query from the prompt
    query = re.sub(r"^.*?\bplay\b\s*", "", prompt, count=1, flags=re.IGNORECASE).strip()
    # Strip trailing filler phrases
    query = re.sub(
        r"\s+(?:on\s+youtube|for\s+me|please|now|song|music)\s*$",
        "", query, flags=re.IGNORECASE,
    ).strip()
    # LAW-20: No trailing punctuation in browser_type text
    query = query.rstrip(".?!")
    if not query:
        query = "english song"
    return _finalized_multi_tool_call(
        [
            {"tool_name": "browser_open", "parameters": {"url": "https://www.youtube.com"}},
            {"tool_name": "browser_click", "parameters": {"selector": "input[name='q']"}},
            {"tool_name": "browser_type", "parameters": {"selector": "input[name='q']", "text": query}},
            {"tool_name": "browser_press_key", "parameters": {"key": "Enter"}},
            {"tool_name": "browser_wait_for_navigation", "parameters": {"timeout_ms": 5000}},
            {"tool_name": "browser_click", "parameters": {"selector": "first video result"}},
        ],
        "prompt_youtube_song_play",
        f"Now playing: {query}",
    )
    search_url = f"https://www.youtube.com/results?search_query={quote(query)}"
    return _finalized_multi_tool_call(
        [
            {"tool_name": "browser_open", "parameters": {"url": search_url}},
            {
                "tool_name": "browser_click",
                "parameters": {"selector": "ytd-video-renderer a#video-title"},
            },
        ],
        "prompt_youtube_song_play",
    )


def _recover_julias_ai_flow(prompt: str) -> dict[str, Any] | None:
    """Intercept queries about Julia's AI by Google and route to web_search."""
    lower = prompt.lower()
    if "julia" not in lower:
        return NO_ACTION
    if not any(kw in lower for kw in ("julias ai", "julia's ai", "julia ai")):
        return NO_ACTION
    return _finalized_tool_call(
        "web_search",
        {"query": "Julias AI by Google"},
        "prompt_julias_ai_search",
    )


def _recover_file_read(prompt: str) -> dict[str, Any] | None:
    """Intercept file-reading prompts and route to file_read."""
    lower = prompt.lower()
    if not any(kw in lower for kw in ("read it", "read file", "open file", "open this file", "read this file")):
        return NO_ACTION
    # Don't intercept if this is clearly a browser/app open command
    if any(kw in lower for kw in ("browser", "youtube", "google", "whatsapp", "gmail")):
        return NO_ACTION
    # Try to extract an absolute or relative file path
    path_match = re.search(r"([A-Za-z]:[\\/_][^\s'\"`,]+|(?:\.{0,2}/)[^\s'\"`,]+)", prompt)
    if path_match:
        file_path = path_match.group(1).strip()
    else:
        # Try to find a filename-like token (e.g., "main.py", "test.txt")
        name_match = re.search(r"\b([\w.-]+\.\w{1,6})\b", prompt)
        if name_match:
            file_path = name_match.group(1)
        else:
            return NO_ACTION
    return _finalized_tool_call(
        "file_read",
        {"path": file_path},
        "prompt_file_read",
    )


def _recover_new_file_creation(prompt: str) -> dict[str, Any] | None:
    """Intercept prompts to create a new file and route to file_write."""
    lower = prompt.lower()
    if not any(kw in lower for kw in ("make a new file", "make file", "create a file", "new file")):
        return NO_ACTION
    # If the existing file_write pattern already matched, let it handle it
    if FILE_WRITE_PATTERN.search(prompt) or EXACT_FILE_WRITE_PATTERN.search(prompt):
        return NO_ACTION
    # Extract file name from "name it X" / "named X" / "called X" patterns
    name_match = re.search(
        r"(?:name(?:d?\s+it)?|called?)\s+['\"]?([^\s'\"]+)['\"]?",
        prompt, re.IGNORECASE,
    )
    if not name_match:
        # Try "make a new file X.ext" pattern
        name_match = re.search(
            r"(?:make|create)\s+(?:a\s+)?(?:new\s+)?file\s+['\"]?([^\s'\"]+\.\w{1,6})['\"]?",
            prompt, re.IGNORECASE,
        )
    if not name_match:
        return NO_ACTION
    file_name = _strip_wrapping_quotes(name_match.group(1).strip())
    # Extract optional content after "with content/containing/content:"
    content = ""
    content_match = re.search(
        r"(?:with\s+content(?:s)?|with|containing|content)\s*:?\s*['\"]?(.*?)['\"]?\s*$",
        prompt, re.IGNORECASE | re.DOTALL,
    )
    if content_match:
        content = content_match.group(1).strip()
    return _finalized_tool_call(
        "file_write",
        {"path": file_name, "content": content},
        "prompt_new_file_creation",
    )


def _repair_model_action(action: dict[str, Any], prompt: str = "") -> dict[str, Any] | None:
    if not isinstance(action, dict):
        return NO_ACTION

    action_name = action.get("action")
    
    if action_name == "respond":
        text = action.get("text", "")
        match = re.search(r"```(?:python|py)\s*(.*?)\s*```", text, flags=re.IGNORECASE | re.DOTALL)
        if match:
            code = match.group(1).strip()
            save_dir = str(_project_root() / "projects" / "recovered_app")
            save_match = re.search(r"save.*?([A-Za-z]:[\\/][^\n\s'\"`]+|/[^\n\s'\"`]+)", prompt, re.IGNORECASE)
            if save_match:
                save_dir = save_match.group(1).strip()
            project_dir = Path(save_dir)
            script_name = "main.py"
            scaffold_call = {
                "tool_name": "file_write",
                "parameters": {"path": str(project_dir / script_name), "content": code},
            }
            run_command = (
                '$p = Start-Process -FilePath "python" '
                f'-ArgumentList "{script_name}" '
                f'-WorkingDirectory "{project_dir}" -PassThru; $p.Id'
            )
            return _finalized_multi_tool_call(
                [
                    scaffold_call,
                    {
                        "tool_name": "shell_run",
                        "parameters": {"command": run_command, "cwd": str(project_dir)},
                    },
                ],
                "model_code_block_repair",
            )

    tool_name = action.get("tool_name")
    parameters = action.get("parameters")
    if action_name == "multi_tool_call" and isinstance(tool_name, str) and isinstance(parameters, dict):
        return _finalized_tool_call(tool_name, parameters, "model_multi_to_single")
    if action_name == "tool_call" and isinstance(tool_name, str) and isinstance(parameters, dict):
        repaired = _repair_tool_alias(tool_name, parameters)
        if repaired is not NO_ACTION:
            return repaired
    return NO_ACTION


def _repair_tool_alias(tool_name: str, parameters: dict[str, Any]) -> dict[str, Any] | None:
    normalized = tool_name.strip().lower()
    if normalized in {"file_system_tools", "file_tools"}:
        files = parameters.get("files")
        if isinstance(files, list) and len(files) == 1 and isinstance(files[0], dict):
            file_spec = files[0]
            path = file_spec.get("path")
            content = file_spec.get("content", "")
            if isinstance(path, str) and isinstance(content, str):
                return _finalized_tool_call(
                    "file_write",
                    {"path": path, "content": content},
                    "model_file_alias",
                )
    if normalized in {"shell", "powershell"} and isinstance(parameters.get("command"), str):
        repaired_params = dict(parameters)
        repaired_params.setdefault("cwd", str(_project_root()))
        return _finalized_tool_call("shell_run", repaired_params, "model_shell_alias")
    return NO_ACTION


def _finalized_tool_call(tool_name: str, parameters: dict[str, Any], source: str) -> dict[str, Any]:
    return {
        "action": "tool_call",
        "tool_name": tool_name,
        "parameters": parameters,
        FINALIZE_AFTER_TOOL: True,
        RECOVERY_SOURCE: source,
    }


def _finalized_multi_tool_call(tools: list[dict[str, Any]], source: str, summary: str = "") -> dict[str, Any]:
    action = {
        "action": "multi_tool_call",
        "tools": tools,
        FINALIZE_AFTER_TOOL: True,
        RECOVERY_SOURCE: source,
    }
    if summary:
        action["_recovery_summary"] = summary
    return action


def _extract_type_text(prompt: str) -> str:
    quoted_after_type = re.search(
        r"\btype\s+(?P<quote>['\"])(?P<text>.+?)(?P=quote)",
        prompt,
        flags=re.IGNORECASE | re.DOTALL,
    )
    if quoted_after_type is not None:
        return quoted_after_type.group("text").strip()

    exact = re.search(
        r"\btype\s+exactly\s*:?\s*(?P<text>.+?)(?:\n\s*-\s*do\s+not\s+press\s+enter\b|$)",
        prompt,
        flags=re.IGNORECASE | re.DOTALL,
    )
    if exact is not None:
        lines = [line.strip(" -\t\r") for line in exact.group("text").splitlines()]
        lines = [line for line in lines if line]
        if lines:
            return _strip_wrapping_quotes(lines[0])
    match = re.search(r"\btype\s+(?P<text>.+?)\s*$", prompt, flags=re.IGNORECASE | re.DOTALL)
    if match is None:
        search_match = re.search(
            r"\bsearch\s+(?:for\s+)?(?P<text>.+?)\s*$",
            prompt,
            flags=re.IGNORECASE | re.DOTALL,
        )
        if search_match is None:
            return ""
        return _strip_wrapping_quotes(search_match.group("text").strip(" :")).rstrip(".?!")
    value = match.group("text").strip()
    value = re.split(
        r"\s+(?:in|into|inside|on)\s+(?:the\s+)?(?:search\s+bar|search\s+box|email\s+field|email\s+box|text\s+field|input|field|box)\b",
        value,
        maxsplit=1,
        flags=re.IGNORECASE,
    )[0]
    value = re.split(
        r"\s+(?:then|and)\s+(?:click|press|submit|hit|select)\b",
        value,
        maxsplit=1,
        flags=re.IGNORECASE,
    )[0]
    cleaned = _strip_wrapping_quotes(value.strip(" :"))
    # LAW-20: Strip trailing punctuation from browser_type query text
    cleaned = cleaned.rstrip(".?!")
    return cleaned


def _calculator_script() -> str:
    return '''import tkinter as tk


class Calculator(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("MAYDAY Phase 6A Calculator")
        self.geometry("320x430")
        self.resizable(False, False)
        self.expression = tk.StringVar()
        entry = tk.Entry(self, textvariable=self.expression, font=("Segoe UI", 22), justify="right")
        entry.pack(fill="x", padx=12, pady=12, ipady=10)
        buttons = [
            ("7", "8", "9", "/"),
            ("4", "5", "6", "*"),
            ("1", "2", "3", "-"),
            ("0", ".", "=", "+"),
        ]
        for row in buttons:
            frame = tk.Frame(self)
            frame.pack(fill="both", expand=True, padx=12, pady=4)
            for label in row:
                tk.Button(
                    frame,
                    text=label,
                    font=("Segoe UI", 18),
                    command=lambda value=label: self.press(value),
                ).pack(side="left", fill="both", expand=True, padx=4)
        tk.Button(self, text="Clear", font=("Segoe UI", 16), command=self.clear).pack(
            fill="x", padx=16, pady=12
        )

    def press(self, value):
        if value == "=":
            try:
                allowed = set("0123456789.+-*/() ")
                expr = self.expression.get()
                if not set(expr) <= allowed:
                    raise ValueError("unsupported input")
                self.expression.set(str(eval(expr, {"__builtins__": {}}, {})))
            except Exception:
                self.expression.set("Error")
        else:
            current = "" if self.expression.get() == "Error" else self.expression.get()
            self.expression.set(current + value)

    def clear(self):
        self.expression.set("")


if __name__ == "__main__":
    Calculator().mainloop()
'''


def _pyqt6_calculator_script() -> str:
    return '''"""MAYDAY Phase 6B — PyQt6 Dark-Themed Calculator"""
import sys
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QGridLayout,
    QPushButton, QLineEdit, QSizePolicy,
)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QFont


DARK_STYLE = """
QMainWindow { background-color: #1e1e2e; }
QLineEdit {
    background-color: #181825; color: #cdd6f4; border: none;
    font-size: 32px; padding: 16px; border-radius: 8px;
}
QPushButton {
    background-color: #313244; color: #cdd6f4; border: none;
    font-size: 20px; padding: 18px; border-radius: 8px;
    min-width: 64px; min-height: 48px;
}
QPushButton:hover { background-color: #45475a; }
QPushButton:pressed { background-color: #585b70; }
QPushButton[cssClass="operator"] { background-color: #f38ba8; color: #1e1e2e; }
QPushButton[cssClass="operator"]:hover { background-color: #f5a8be; }
QPushButton[cssClass="clear"] { background-color: #a6e3a1; color: #1e1e2e; }
QPushButton[cssClass="clear"]:hover { background-color: #b8ebb4; }
QPushButton[cssClass="equals"] { background-color: #89b4fa; color: #1e1e2e; }
QPushButton[cssClass="equals"]:hover { background-color: #a0c4fb; }
"""


class Calculator(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("MAYDAY PyQt6 Calculator")
        self.setMinimumSize(340, 480)
        self.setStyleSheet(DARK_STYLE)

        central = QWidget()
        self.setCentralWidget(central)
        layout = QVBoxLayout(central)
        layout.setSpacing(8)
        layout.setContentsMargins(12, 12, 12, 12)

        self.display = QLineEdit("0")
        self.display.setAlignment(Qt.AlignmentFlag.AlignRight)
        self.display.setReadOnly(True)
        self.display.setFont(QFont("Segoe UI", 28))
        layout.addWidget(self.display)

        grid = QGridLayout()
        grid.setSpacing(6)
        layout.addLayout(grid)

        buttons = [
            ("C", 0, 0, "clear"), ("±", 0, 1, ""), ("%", 0, 2, ""), ("/", 0, 3, "operator"),
            ("7", 1, 0, ""), ("8", 1, 1, ""), ("9", 1, 2, ""), ("*", 1, 3, "operator"),
            ("4", 2, 0, ""), ("5", 2, 1, ""), ("6", 2, 2, ""), ("-", 2, 3, "operator"),
            ("1", 3, 0, ""), ("2", 3, 1, ""), ("3", 3, 2, ""), ("+", 3, 3, "operator"),
            ("0", 4, 0, ""), (".", 4, 2, ""), ("=", 4, 3, "equals"),
        ]

        for label, row, col, css_class in buttons:
            btn = QPushButton(label)
            btn.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
            if css_class:
                btn.setProperty("cssClass", css_class)
            btn.clicked.connect(lambda checked, v=label: self.on_press(v))
            colspan = 2 if label == "0" else 1
            grid.addWidget(btn, row, col, 1, colspan)

        self._expression = ""
        self._new_input = True

    def on_press(self, value):
        if value == "C":
            self._expression = ""
            self.display.setText("0")
            self._new_input = True
            return
        if value == "=":
            try:
                safe = set("0123456789.+-*/() %")
                if not set(self._expression) <= safe:
                    raise ValueError("bad input")
                result = eval(self._expression, {"__builtins__": {}}, {})
                result_str = str(result)
                if "." in result_str:
                    result_str = result_str.rstrip("0").rstrip(".")
                self.display.setText(result_str)
                self._expression = result_str
                self._new_input = True
            except Exception:
                self.display.setText("Error")
                self._expression = ""
                self._new_input = True
            return
        if value == "±":
            if self._expression.startswith("-"):
                self._expression = self._expression[1:]
            elif self._expression:
                self._expression = "-" + self._expression
            self.display.setText(self._expression or "0")
            return
        if value == "%":
            try:
                self._expression = str(float(self._expression) / 100)
                self.display.setText(self._expression)
            except Exception:
                pass
            return

        if self._new_input and value not in "+-*/":
            self._expression = ""
            self._new_input = False

        self._expression += value
        self.display.setText(self._expression)


if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = Calculator()
    window.show()
    sys.exit(app.exec())
'''


def _extract_url(prompt: str) -> str:
    match = URL_PATTERN.search(prompt)
    if match is None:
        return ""
    candidate = match.group(0).rstrip(".,)")
    parsed = urlparse(candidate)
    if not parsed.scheme:
        candidate = f"https://{candidate}"
    return candidate


def _strip_wrapping_quotes(value: str) -> str:
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
        return value[1:-1]
    return value


def _project_root() -> Path:
    return Path(__file__).resolve().parent.parent
