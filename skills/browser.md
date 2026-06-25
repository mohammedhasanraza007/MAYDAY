---
triggers: [browser, web, navigate, click, search, url, website, youtube, whatsapp, gmail, scroll]
---
BROWSER AUTOMATION RULES:
- Always call browser_open first before any click/type actions.
- After browser_press_key("Enter") always call browser_wait_for_navigation() next.
- After browser_wait_for_navigation() call browser_get_text() to read results.
- For YouTube: open -> click search -> type query -> press Enter -> wait -> click first video -> respond.
- For forms: click field -> type content -> press Tab or Enter -> wait -> verify.
- Max browser depth: 5 navigations per task. If stuck, call browser_close and start fresh.
- Never guess page content. Always call browser_get_text() before responding about what a page shows.
