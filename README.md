🌌 M.A.Y.D.A.Y — Modular Agentic Yield & Desktop Automation Yard

[![Local GGUF CPU](https://img.shields.io/badge/Model-Local%20GGUF%20CPU-blueviolet?style=for-the-badge)](#local-inference-layer)
[![PyQt6 Desktop Interface](https://img.shields.io/badge/GUI-PyQt6%20Desktop-blue?style=for-the-badge)](#desktop-gui-workspace)
[![Playwright Automation](https://img.shields.io/badge/Automation-Playwright-orange?style=for-the-badge)](#browser-automation)
[![No-Mocks Safety Guard](https://img.shields.io/badge/Execution-Safety%20Gated-red?style=for-the-badge)](#safety-gateway--permission-controls)
[![License MIT](https://img.shields.io/badge/License-MIT-green?style=for-the-badge)](#license)

M.A.Y.D.A.Y (Modular Agentic Yield & Desktop Automation Yard) is an offline-first autonomous software engineering agent and system automation workbench. Running locally on consumer hardware, Mayday uses CPU-quantized GGUF models (`Qwen2.5-Coder`) and a modular PyQt6 desktop workspace to convert natural language objectives into physical, verified actions on your local operating system.

Unlike chat-based LLM interfaces that return static markdown code blocks, Mayday operates within a strict **Observe → Act → Verify** loop. The agent has direct tool access to write, patch, and execute source code; automate browser interactions; manage local web servers; and perform desktop-level clicks, keyboard input, and file manipulations. All execution runs under a robust, user-gated safety approval dialog.

---

## 📸 Presentation & Live Execution Gallery

Every image below is a real screenshot captured from the active PyQt6 application and browser automation windows during live execution of the Mayday test suite.

### 1. Application Startup & Verification
The initial desktop interface verifying loaded configurations, active local model tiers, system RAM monitors, and service status.
<img width="3072" height="1728" alt="startup-proof" src="https://github.com/user-attachments/assets/53b34fe9-515b-4e20-9a6e-949ca6d75802" />


### 2. Home Screen
The clean, modern PyQt6 chat workspace showing the primary prompt input and the model integration status bar.

<img width="3072" height="1728" alt="main-window" src="https://github.com/user-attachments/assets/4945938d-6552-4af5-9b57-448a4e2f9786" />


### 3. Browser Automation Driver
The Playwright driver executing atomic browser operations, highlighting DOM elements and performing page interactions.

<img width="3072" height="1728" alt="browser-test" src="https://github.com/user-attachments/assets/da0c8829-9f93-4fff-9eb8-b5b5a260f7b6" />

### 4. Calculator Generation — Result
The dark-themed glassmorphic calculator rendered live in a local browser session.
<img width="552" height="725" alt="image" src="https://github.com/user-attachments/assets/5e2088f1-c257-4105-bdc3-6b883d195fc0" />


### 5. Game Generation — Result
The neon-styled Tic-Tac-Toe game scaffolded, hosted, and verified by Mayday in a live browser session.

<img width="800" height="600" alt="game" src="https://github.com/user-attachments/assets/04c9cb34-1649-465d-8cd4-06aad6e9acde" />


---

## 🧪 Interaction & Execution Test Trace Outputs

Below are the request and execution stages captured during live interactive test tasks.

#### Test 1: File creation
* **Input Request**: Create a file called `test.txt` with `hello world`
* **Request & Execution**: <img width="1400" height="787" alt="file-operation" src="images/file-operation.png" />
* **Result Screenshot**: <img width="1400" height="787" alt="file-operation-response" src="images/file-operation-response.png" />

#### Test 2: Browser navigation
* **Input Request**: Open `https://www.wikipedia.org`
* **Execution Screenshot**: <img width="1400" height="787" alt="browser-test" src="images/browser-test.png" />

#### Test 3: Calculator creation
* **Input Request**: Create a simple calculator in `projects/calc`
* **Request Capture**: <img width="3086" height="1742" alt="calculator-request" src="https://github.com/user-attachments/assets/6c675695-6b4c-4025-83d8-d59cfa43c8aa" />

* **Execution Screenshot**: <img width="3072" height="1728" alt="file-operation-response" src="https://github.com/user-attachments/assets/8cb072c3-e010-483c-b6d0-0aa6e582fcef" />

* **Result Screenshot**: <img width="552" height="725" alt="image" src="https://github.com/user-attachments/assets/fcdea949-d786-44b0-be7d-43c05daeec1d" />



#### Test 4: Game creation
* **Input Request**: Create a Tic-Tac-Toe game in `projects/game`
* **Result Screenshot**: <img width="800" height="600" alt="game" src="https://github.com/user-attachments/assets/eb899db0-12a8-4e4b-9f0d-47387f032b0a" />



---

## 📋 Capability & Tool Registry Matrix

Mayday's features are verified on disk and in memory. The table below maps each domain capability to its backend implementation.

| Functional Domain | Registered Tool | Implementation | Python Dependencies | Capability Description |
| :--- | :--- | :--- | :--- | :--- |
| **Web Automation** | `browser_*` | `tools/browser_tools.py` | `playwright` (Sync API) | Navigates URLs, clicks selectors, types input values, triggers keypresses, scrolls pages, captures screenshots, and extracts inner text/HTML elements. |
| **Desktop Automation** | `system_*` | `tools/system_tools.py` | `pyautogui`, `pywinauto`, `psutil` | OS-level coordinate clicking, keyboard events, key combinations (Alt+Tab, Ctrl+C), full desktop snapshots, and active process listing. |
| **Office Operations** | `excel_*` | `tools/excel_tools.py` | `pandas`, `openpyxl` | Generates `.xlsx` spreadsheet files from tabular JSON data, reads worksheets, and appends cell ranges to existing structures. |
| **Code Generation** | `scaffold`, `project` | `runtime/scaffold_engine.py` | `os`, `pathlib` | Scaffolds directory layouts and generates template codebases for modern stacks (FastAPI, Flask, Static HTML/JS/CSS). |
| **Preview Hosting** | `server_*` | `runtime/server_runner.py` | `subprocess`, `socket`, `httpx` | Detects open system ports dynamically, launches web servers, monitors process health, and pings until HTTP 200 is verified. |
| **File Manipulation** | `file_*` | `tools/file_tools.py` | `os`, `pathlib` | Writes text, reads paths, deletes files, lists directories, and performs line-by-line insertions or block replacements. |
| **Shell Access** | `shell_run`, `powershell_*` | `tools/shell_tools.py` | `subprocess` | Runs safe system subprocesses under `cmd` or PowerShell with custom timeouts (default 30s) and captures stdout/stderr. |
| **Communications** | `gmail_*`, `calendar_*` | `tools/gmail_tools.py` | `google-api-python-client` | Lists unread email headers, extracts body contents, and schedules calendar events. |

---

## ⚙️ Architectural Diagrams

Mayday separates user interaction, model reasoning, action permissions, and tool execution into distinct system layers.

### 1. Modular System Architecture
The relationship between PyQt6 presentation widgets, the central Orchestrator loop, GBNF action constraints, safety gates, and local GGUF/API models.

<img width="800" height="500" alt="architecture" src="https://github.com/user-attachments/assets/a772c89c-0097-45ad-8004-cbdf7058676e" />


### 2. Tool Pipeline Execution
The process a tool payload traverses, from schema validation through thread dispatch to environment state verification.

<img width="800" height="500" alt="tool exc pipline" src="https://github.com/user-attachments/assets/7201b8f8-4113-4e3c-83e2-72abbeee2fd2" />


### 3. Memory and Context Flow
The three-tier memory architecture that routes tokens through working memory, context summaries, and disk-archived episodes.

<img width="800" height="500" alt="memory and context flow" src="https://github.com/user-attachments/assets/419771c7-6d06-49ec-a780-7c45724d8824" />


---

## 🚀 Installation & Quick Start

Mayday is built to run on Windows systems. Ensure Python 3.10+ is installed and on your system path.

### 1. One-Click Bootstrap
The recommended method uses the self-healing bootstrap batch script in the repository root. It auto-detects system paths, creates a virtual environment, installs dependencies, and downloads model weights.

```powershell
.\build.bat
```

### 2. Manual Installation
If you prefer to configure your workspace manually:

```powershell
# 1. Create a Python Virtual Environment
python -m venv .venv
.venv\Scripts\activate

# 2. Upgrade Packaging Prerequisites
python -m pip install --upgrade pip setuptools wheel

# 3. Install Pin-Locked Requirements
pip install -r requirements.txt

# 4. Install Playwright Web Browser Drivers
python -m playwright install chromium
```

### 3. Verification Launch
Validate that local GGUF weights load into memory and run inference successfully:

```powershell
.venv\Scripts\python.exe main.py --verify
```

### 4. Standard GUI Launch
Run the primary PyQt6 desktop workspace:

```powershell
.venv\Scripts\python.exe main.py
```

---

## 🛠️ Configuration & Environment Variables

System parameters are controlled through environment variables or configured in the **API** tab of the dashboard.

| Environment Variable | Supported Values | Default | Functional Impact |
| :--- | :--- | :--- | :--- |
| `MAYDAY_SAFE_MODE` | `0` or `1` | `0` | When `1`, skips GGUF weight loading and boots into lightweight API fallback state. |
| `MAYDAY_BROWSER_HEADLESS` | `true` or `false` | `false` | Runs the Playwright driver headless (invisible) or headful (visible browser window). |
| `MAYDAY_BROWSER_EXECUTABLE` | Absolute path | Auto-detected | Forces Playwright to use a specific browser binary (Chrome, Brave, Edge) instead of packaged Chromium. |
| `MAYDAY_ROOT` | Absolute path | Directory of `build.bat` | Establishes the base directory for file resolution patterns, preventing absolute path hardcoding. |
| `MAYDAY_ACTION_MAX_TOKENS` | Integer | `200` | Limits model token generation per action step to prevent text filler in structured outputs. |

---

## 🔒 Safety Gateway & Permission Controls

Security is a primary concern for a local agent with file manipulation and terminal access. Mayday enforces safety through a classification-based authorization grid and a GUI gateway prompt.

### 1. Capability Classifications
Tools are assigned capability levels in `runtime/execution_registry.py`:

*   **safe** — Non-destructive operations (`file_read`, `web_search`, `system_info`). Executed immediately without prompting.
*   **restricted** — Destructive or system-mutating operations (`shell_run`, `file_delete`, `powershell_run`, `system_click`). Require explicit approval.
*   **sandbox_only** — Operations restricted to the `projects/` output directory.

### 2. Safety Permission Prompt
When a **restricted** tool is invoked, the execution loop pauses. The PyQt6 thread intercepts the action and displays a graphical gateway dialog:

*   **Allow** — Executes the current step only.
*   **Allow Always** — Grants execution permission for this specific tool for the remainder of the current session.
*   **Deny** — Aborts the step, returns a cancellation error, and forces the model to replan.

---

## 🧠 Reasoning & GBNF Grammar Controls

To eliminate JSON parsing failures common in locally quantized models, Mayday forces output formatting using context-free grammars.

### 1. Intent Router Pre-Classification
Before invoking the model, `core/intent_router.py` classifies the query using keyword rules into one of four categories:

*   `PROJECT_CREATION`
*   `EXECUTION_COMMANDS`
*   `AUTOMATION_COMMANDS`
*   `FILE_OPERATIONS`

This pre-classification selects the correct subset of system tools and the appropriate system prompt for the current task.

### 2. GBNF Action Grammar (`grammar/action.gbnf`)
During task execution, Mayday forces the model to output a single JSON block matching a precise schema. This is achieved by loading a GBNF grammar definition at inference time:

```gbnf
root ::= ws action ws
ws ::= [ \t\n\r]*
action ::= tool-call | multi-call | respond-action
tool-call ::= "{" ws "\"action\"" ws ":" ws "\"tool_call\"" ws "," ws "\"tool_name\"" ws ":" ws tool-name ws "," ws "\"parameters\"" ws ":" ws object ws "}"
tool-name ::= "\"browser_open\"" | "\"browser_click\"" | "\"file_write\"" | "\"shell_run\"" | "\"server_launch\""
```

By constraining model decoding to this grammar, JSON parsing errors are eliminated entirely.

---

## 💾 Memory Hierarchy & Context Management

To prevent context window overflow (4096 tokens for GGUF models), Mayday uses a three-tier memory architecture rather than simple chat history truncation.

### 1. Active Working Memory
The last 20 conversational turns are held in the live context window, ensuring the model retains immediate instructions and terminal outputs.

### 2. Hierarchical Condenser (`memory/condenser.py`)
Turns older than the working memory window are processed by `HierarchicalCondenser`. It compresses batches into three-sentence summaries, preserving key file paths, tool actions, and terminal success statuses. Condensed summaries are re-injected into context as prior history.

### 3. Episode Archive (`memory/episodes/`)
Compressed session histories are serialized to JSON files on disk. On application restart, the most recent episode is loaded as prior session context, giving the model continuity across separate runs.

### 4. Failure Memory
Failed tool calls are tracked by hashing the tool name and arguments. If the identical call fails twice, the orchestrator raises a `RecoveryException` and forces a replanning step rather than retrying indefinitely.

---

## 📂 Repository File Directory

```
MAYDAY/
├── bootstrap/
│   └── bootstrap_ui.py          # Self-healing installer UI
├── core/                        # Central orchestration & logic
│   ├── context_compressor.py    # Word-count based context helper
│   ├── event_stream.py          # Pub/sub event stream dispatcher
│   ├── exceptions.py            # Central exception definitions
│   ├── intent_router.py         # Keyword classification-based tool router
│   ├── json_parser.py           # Robust JSON parsing fallback
│   ├── orchestrator.py          # Main reasoning & execution loop
│   ├── session.py               # Active context manager
│   ├── skill_loader.py          # Skill registration
│   └── tool_recovery.py         # Prompt-based JSON recovery parser
├── grammar/
│   └── action.gbnf              # GBNF constraints for action output
├── images/                      # Documentation screenshots
├── memory/
│   ├── episodes/                # Disk-archived session summaries (JSON)
│   └── condenser.py             # Hierarchical memory compressor
├── model/
│   ├── downloader.py            # GGUF model download client
│   └── loader.py                # CPU/GPU RAM preflight checker & loader
├── runtime/
│   ├── action_schema.py         # Action type definitions
│   ├── engine.py                # Action dispatch manager
│   ├── execution_budget.py      # Step limit enforcement
│   ├── execution_registry.py    # Tool contract validation registry
│   ├── scaffold_engine.py       # Project scaffolder
│   ├── server_runner.py         # Live web server preview hosting
│   └── state_snapshot.py        # Filesystem change tracker
├── skills/                      # Custom microagent skill files
├── tests/                       # Pytest test suite
├── tools/
│   ├── base_tool.py             # Base tool class contract
│   ├── browser_tools.py         # Playwright web automation
│   ├── excel_tools.py           # pandas spreadsheet reader/writer
│   ├── file_tools.py            # Filesystem operations
│   ├── gmail_tools.py           # Gmail and Calendar tools
│   ├── shell_tools.py           # Safe subprocess executor
│   └── system_tools.py          # PyAutoGUI desktop controller
├── ui/
│   ├── main_window.py           # Main PyQt6 interface layout
│   ├── panels.py                # Panel widgets (Chat, Logs, Dashboard, etc.)
│   └── theme.py                 # Dark theme stylesheet definitions
├── build.bat                    # Portable bootstrap launcher
├── main.py                      # Entry point (GUI / --verify mode)
├── requirements.txt             # Pin-locked project dependencies
└── README.md
```

---

## 📈 Verified Task Execution Workflows

Step-by-step trace files for common tasks, detailing how they are executed through Mayday's tool pipeline.

### Task A: Open a Website & Fetch Content
1. **User Prompt**: "Open the website `https://www.wikipedia.org` and get its main heading text."
2. **Intent Classifier**: Matches `AUTOMATION_COMMANDS` (requires `browser_open`, `browser_get_text`).
3. **Action Generation**: Model outputs `{"action":"tool_call","tool_name":"browser_open","parameters":{"url":"https://www.wikipedia.org"}}`
4. **Security Gate**: Classified as `safe` (web read). Executed immediately.
5. **Execution**: Playwright launches Chromium, navigates to the URL, returns a page screenshot.
6. **Next Action**: Model parses the screenshot observation and outputs `{"action":"tool_call","tool_name":"browser_get_text","parameters":{"selector":"h1"}}`
7. **Observation**: Returns `{"status":"success","text":"Wikipedia"}`.
8. **Completion**: Model outputs `{"action":"respond","text":"The heading of Wikipedia is 'Wikipedia'."}`.

### Task B: Create a Glassmorphic Calculator App
1. **User Prompt**: "Create a dark-themed glassmorphic calculator in `projects/calc`."
2. **Intent Classifier**: Matches `PROJECT_CREATION` (requires `scaffold`).
3. **Action Generation**: Model outputs a `scaffold` tool call with a `files` parameter.
4. **Security Gate**: Classified as `restricted` (writing files). GUI displays permission prompt. User clicks **Allow**.
5. **Execution**: `scaffold_engine` writes files to `projects/calc/` (HTML, JS, CSS structures).
6. **Next Action**: Model outputs `{"action":"tool_call","tool_name":"server_launch","parameters":{"project_dir":"projects/calc","stack":"static"}}`
7. **Execution**: `server_runner` scans ports, launches a server process, pings it, and returns the active port.
8. **Completion**: Playwright opens the local server URL and takes a screenshot of the rendered calculator page.

### Task C: Create a Tic-Tac-Toe Game
1. **User Prompt**: "Create a Tic-Tac-Toe game in `projects/game`."
2. **Intent Classifier**: Matches `PROJECT_CREATION` (requires `scaffold`).
3. **Action Generation**: Generates neon grid styling and game logic file payloads.
4. **Security Gate**: Requires user confirmation. Approved.
5. **Execution**: `scaffold_engine` writes all source files.
6. **Next Action**: Model launches a local static server and navigates Playwright to the hosted URL.
7. **Completion**: Captures the rendered game grid, confirming correct layout and styling.

### Task D: Write & Run a Python Script
1. **User Prompt**: "Write a Python script to calculate Fibonacci and run it to verify."
2. **Intent Classifier**: Matches `EXECUTION_COMMANDS` (requires `file_write`, `shell_run`).
3. **Action Generation**: Writes code to `projects/fib.py`.
4. **Security Gate**: User approves file write.
5. **Next Action**: Invokes `{"action":"tool_call","tool_name":"shell_run","parameters":{"command":"python projects/fib.py"}}`
6. **Security Gate**: GUI displays shell command warning. User clicks **Allow**.
7. **Execution**: Runs Python process, returns exit code `0` and stdout: `[0, 1, 1, 2, 3, 5, 8]`.
8. **Completion**: Model summarises the verified run results.

### Task E: Append to an Existing File
1. **User Prompt**: "Append a print statement to `projects/fib.py`."
2. **Intent Classifier**: Matches `FILE_OPERATIONS` (requires `file_patch` or `file_write`).
3. **Action Generation**: Generates block replacement arguments targeting the file's end.
4. **Security Gate**: User confirms.
5. **Execution**: Modifies `projects/fib.py` and returns the updated file size on disk.

---

## ⚠️ System Limitations & Constraints

*   **CPU Performance**: Quantized GGUF inference runs on CPU threads. Token generation rates vary from 2–15 tokens/sec depending on CPU core count and clock speed.
*   **System RAM**: If available system RAM is below 2.5 GB, local model loading is skipped and the application defaults to **Safe Mode**, requiring an external API key.
*   **Playwright Drivers**: Browser automation requires Playwright Chromium drivers. If missing, install them with `python -m playwright install chromium`.
*   **Display Scaling**: Coordinate-based clicking via PyAutoGUI depends on screen resolution. Running inside nested VMs or RDP sessions with non-100% scaling may offset click coordinates.

---

## ❓ Frequently Asked Questions

**Q: Why does Mayday report "Safe Mode" at startup?**

`model/loader.py` checks available system RAM during initialisation. If free RAM is below the 2.5 GB threshold, local GGUF loading is disabled to prevent system paging and instability. Configure an external API key in the **API** panel to operate in Safe Mode.

**Q: How do I enable GPU acceleration for local GGUF models?**

Install `llama-cpp-python` built with CUDA, Vulkan, or DirectML backend flags. `model/loader.py` auto-detects available GPU libraries at startup and offloads model layers to VRAM when conditions allow. Priority order: DirectML → Vulkan → CUDA → CPU.

**Q: Can I run Mayday without the GUI?**

Yes. Run `main.py --verify` for a headless verification check, or interface with the engine directly via the CLI:

```powershell
.venv\Scripts\python.exe -c "from runtime.engine import ExecutionEngine; print(ExecutionEngine())"
```

**Q: Where are agent-created files stored?**

By default, `scaffold_engine.py` and `file_write` tools are restricted to the `projects/` subdirectory inside the repository root, ensuring isolation from system files.

---

## 🤝 Contributing

Contributions are welcome. Please follow these guidelines:

1. Fork the repository.
2. Create your feature branch: `git checkout -b feature/my-feature`
3. Commit your changes: `git commit -m 'feat: add support for custom tool'`
4. Push to the branch: `git push origin feature/my-feature`
5. Submit a Pull Request.

New tools must declare a `base_tool.py` contract, register in `execution_registry.py` with an appropriate capability class, and include Pytest coverage in `tests/`.

---

## 📄 License

This project is licensed under the MIT License — see the `LICENSE` file for details.

## 🤝 Credits & Acknowledgements

*   **Qwen Team** — Qwen2.5-Coder model series
*   **llama.cpp contributors** — High-performance CPU GGUF inference
*   **PyQt6 maintainers** — Desktop GUI framework
*   **Playwright maintainers** — Browser automation framework
