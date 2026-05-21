# M.A.Y.D.A.Y v5.0 — CPU-Quantized Agentic Coding Environment

> **STATUS: BETA**
> M.A.Y.D.A.Y is currently in its Beta development phase. While core orchestration and safety systems are stabilized, users may encounter edge-case behaviors during complex multi-tool executions.

## Overview

**M.A.Y.D.A.Y (Mobile Agentic Yield & Development Assembly Yard)** is a high-performance, professional-grade coding agent designed for local-first execution. Unlike traditional agents that rely heavily on cloud APIs, M.A.Y.D.A.Y is optimized for **CPU-quantized GGUF models**, providing a robust development environment that respects privacy and operates without the need for expensive GPU hardware or constant internet connectivity.

Built with a focus on safety, transparency, and architectural elegance, M.A.Y.D.A.Y enables developers to scaffold entire projects, automate browser-based workflows, and execute system-level operations within a strictly governed sandbox.

---

## Core Capabilities

### 1. Local GGUF Inference
*   **No-Torch Architecture:** Optimized for `llama-cpp-python`, eliminating the heavy footprint of `transformers` or `torch`.
*   **Multi-Tiered Model Support:** Intelligent model loader that selects the best available quantized model based on system resources.
*   **LoRA Management:** Built-in support for ingesting custom datasets and loading GGUF adapters to specialize the agent's coding performance.

### 2. Advanced Agentic Orchestration
*   **Phase 4 Orchestrator:** Implements a sophisticated loop that handles intent classification, tool recovery, and context compression.
*   **Multi-Tool Execution:** Supports `multi_tool_call` for atomic, sequential execution of complex tasks (e.g., scaffolding a backend followed by a server launch).
*   **Task Complexity Analysis:** Automatically routes simple tasks to local models and offers escalation paths for high-complexity requests.

### 3. Integrated Toolset
*   **Project Scaffolding:** Atomic generation of multi-file projects with built-in verification and manifest generation.
*   **Secure Browser Automation:** Managed Playwright integration for web search, data fetching, and interactive automation.
*   **System & PowerShell Tools:** Controlled execution of shell commands and scripts with real-time output capture.

### 4. Professional Safety Gateway
*   **Permission Gate:** Every sensitive action (file writes, shell commands, browser navigations) requires explicit user approval.
*   **Path-Based Security:** Hard-coded protection for system directories (Windows, Program Files, etc.) and restricted root execution.
*   **Audit Logging:** Comprehensive logging of all tool interactions and model decisions for full transparency.

---

## Technical Architecture

M.A.Y.D.A.Y is architected as a decoupled, multi-layered system:

*   **UI Layer (PyQt6):** A modern, asynchronous desktop interface providing real-time telemetry, model management, and interactive chat.
*   **Core Orchestrator:** The brain of the system, managing the `Agentic Loop`, intent routing, and state management.
*   **Runtime Engine:** The execution layer where tools are registered, validated, and safely dispatched.
*   **Model Router:** A decision-making component that balances local inference speed with optional API escalation.

---

## Getting Started

### Prerequisites
*   Python 3.10+
*   (Recommended) Virtual Environment

### Installation
1.  **Clone the repository.**
2.  **Install dependencies:**
    ```bash
    pip install --upgrade pip setuptools wheel
    pip install -r requirements.txt
    ```
3.  **Run the application:**
    ```bash
    python main.py
    ```

### Verification
To verify the integrity of the model backend without launching the GUI:
```bash
python main.py --verify
```

---

## Documentation & Logs
*   **Startup Logs:** Located in `logs/startup_trace.log`.
*   **Session State:** Persisted in `runtime/world_state.json`.
*   **Project Assets:** Generated projects are stored in the `projects/` directory.

---

*M.A.Y.D.A.Y v5.0 — Redefining Local Agentic Development.*
