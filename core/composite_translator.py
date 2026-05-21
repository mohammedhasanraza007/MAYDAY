"""
M.A.Y.D.A.Y Composite Action Translator — Stage 7A
====================================================
Translates model-hallucinated composite/planner actions into ONLY valid
registered atomic execution chains. Planner concepts (browser_act, browser_chain,
multi_browser, etc.) are NEVER preserved — they are decomposed into real tools
or rejected outright.

Allowed atomic tools for browser domain:
    browser_open, browser_click, browser_type, browser_navigate,
    browser_get_text, browser_screenshot, browser_close

Allowed atomic tools for system domain:
    system_click, system_type, system_hotkey, system_info, system_screenshot

All other tool names pass through only if they exist in KNOWN_TOOLS.
"""
from __future__ import annotations

import logging
from typing import Any

from runtime.action_schema import KNOWN_TOOLS

logger = logging.getLogger("mayday.translator")

# Planner-only pseudo-tools that must NEVER reach execution
PLANNER_PSEUDO_TOOLS = {
    "browser_act", "browser_chain", "browser_multi", "browser_sequence",
    "browser_plan", "browser_steps", "multi_browser", "automation_chain",
}

# Mapping from browser_act step actions to real atomic tool names
STEP_ACTION_TO_TOOL = {
    "open": "browser_open",
    "navigate": "browser_navigate",
    "click": "browser_click",
    "type": "browser_type",
    "wait_for": "browser_click",  # wait_for maps to click with retry semantics
    "get_text": "browser_get_text",
    "screenshot": "browser_screenshot",
    "press": "browser_type",  # press maps to type with key semantics
    "extract_meet_link": "browser_get_text",
    "detect_login_state": "browser_get_text",
}


class CompositeActionTranslator:
    """Translates composite planner outputs into valid atomic execution chains.

    Rules:
    1. Planner pseudo-tools (browser_act, etc.) are DECOMPOSED into atomic tools
    2. Only KNOWN_TOOLS survive translation
    3. Microstep mode limits output to a single atomic action
    4. Unknown/hallucinated tools are rejected (returns None)
    """

    @staticmethod
    def translate(action: dict[str, Any], enforce_microstep: bool = False) -> dict[str, Any] | None:
        """Translate model output into compliant atomic execution format.

        Returns None if the action is completely invalid and should be rejected.
        """
        if not isinstance(action, dict):
            return None

        action_name = action.get("action", "")

        # ── Pass through valid respond actions ────────────────────────
        if action_name == "respond":
            return action

        # ── Handle root-level planner pseudo-tools ────────────────────
        if action_name in PLANNER_PSEUDO_TOOLS:
            return CompositeActionTranslator._decompose_planner_action(action, enforce_microstep)

        # ── Handle tool_call wrapping a planner pseudo-tool ───────────
        if action_name == "tool_call":
            tool_name = action.get("tool_name", "")
            if tool_name in PLANNER_PSEUDO_TOOLS:
                params = action.get("parameters", {})
                pseudo = {"action": tool_name, **params}
                return CompositeActionTranslator._decompose_planner_action(pseudo, enforce_microstep)

            # Validate tool_name is a real registered tool
            if tool_name not in KNOWN_TOOLS:
                logger.warning("Rejecting hallucinated tool_call: %s", tool_name)
                return None
            return action

        # ── Handle multi_tool_call ────────────────────────────────────
        if action_name == "multi_tool_call":
            # Fix steps/tools alias
            tools = action.get("tools") or action.get("steps") or []
            if not isinstance(tools, list) or not tools:
                return None

            atomic_tools = []
            for entry in tools:
                if not isinstance(entry, dict):
                    continue
                t_name = entry.get("tool_name", entry.get("name", ""))
                t_params = entry.get("parameters", entry.get("args", {}))

                if t_name in PLANNER_PSEUDO_TOOLS:
                    # Decompose inline pseudo-tools
                    decomposed = CompositeActionTranslator._decompose_planner_action(
                        {"action": t_name, **(t_params if isinstance(t_params, dict) else {})},
                        enforce_microstep=False,
                    )
                    if decomposed and decomposed.get("action") == "multi_tool_call":
                        atomic_tools.extend(decomposed.get("tools", []))
                    elif decomposed and decomposed.get("action") == "tool_call":
                        atomic_tools.append({
                            "tool_name": decomposed["tool_name"],
                            "parameters": decomposed.get("parameters", {}),
                        })
                elif t_name in KNOWN_TOOLS:
                    atomic_tools.append({"tool_name": t_name, "parameters": t_params})
                else:
                    logger.warning("Dropping hallucinated tool from multi_tool_call: %s", t_name)

            if not atomic_tools:
                return None

            if enforce_microstep:
                first = atomic_tools[0]
                logger.info("Microstep: decomposed multi_tool_call to single atomic tool: %s", first["tool_name"])
                return {
                    "action": "tool_call",
                    "tool_name": first["tool_name"],
                    "parameters": first["parameters"],
                }

            return {"action": "multi_tool_call", "tools": atomic_tools}

        # ── Handle bare known tool names as action ────────────────────
        if action_name in KNOWN_TOOLS and action_name not in PLANNER_PSEUDO_TOOLS:
            params = {k: v for k, v in action.items() if k != "action"}
            return {
                "action": "tool_call",
                "tool_name": action_name,
                "parameters": params,
            }

        # ── Unknown action — reject ──────────────────────────────────
        if action_name and action_name not in {"respond", "tool_call", "multi_tool_call"}:
            logger.warning("Rejecting unknown action type: %s", action_name)
            return None

        return action

    @staticmethod
    def _decompose_planner_action(
        action: dict[str, Any], enforce_microstep: bool
    ) -> dict[str, Any] | None:
        """Decompose a planner pseudo-action (like browser_act) into atomic tool calls."""
        steps = action.get("steps", [])
        if not isinstance(steps, list) or not steps:
            # Single-step pseudo-action with URL — convert to browser_open
            url = action.get("url")
            if isinstance(url, str) and url.strip():
                return {
                    "action": "tool_call",
                    "tool_name": "browser_open",
                    "parameters": {"url": url},
                }
            logger.warning("Planner pseudo-action has no decomposable steps")
            return None

        atomic_tools = []
        for step in steps:
            if not isinstance(step, dict):
                continue
            step_action = step.get("action", "")
            tool_name = STEP_ACTION_TO_TOOL.get(step_action)
            if not tool_name:
                logger.warning("Unknown step action in planner decomposition: %s", step_action)
                continue

            params: dict[str, Any] = {}
            if tool_name in ("browser_open", "browser_navigate"):
                url = step.get("url", "")
                if isinstance(url, str) and url.strip():
                    params["url"] = url
                else:
                    continue  # skip steps without valid URL
            elif tool_name in ("browser_click",):
                selector = step.get("selector", "")
                if isinstance(selector, str) and selector.strip():
                    params["selector"] = selector
                else:
                    continue
            elif tool_name in ("browser_type",):
                selector = step.get("selector", "")
                text = step.get("text", step.get("value", step.get("key", "")))
                if isinstance(selector, str) and selector.strip():
                    params["selector"] = selector
                    params["text"] = str(text) if text else ""
                else:
                    continue
            elif tool_name in ("browser_get_text",):
                selector = step.get("selector", "body")
                params["selector"] = selector if isinstance(selector, str) else "body"
            elif tool_name in ("browser_screenshot",):
                pass  # no params needed

            atomic_tools.append({"tool_name": tool_name, "parameters": params})

        if not atomic_tools:
            return None

        if enforce_microstep:
            first = atomic_tools[0]
            logger.info(
                "Microstep: decomposed planner pseudo-action to single atomic: %s",
                first["tool_name"],
            )
            return {
                "action": "tool_call",
                "tool_name": first["tool_name"],
                "parameters": first["parameters"],
            }

        if len(atomic_tools) == 1:
            return {
                "action": "tool_call",
                "tool_name": atomic_tools[0]["tool_name"],
                "parameters": atomic_tools[0]["parameters"],
            }

        return {"action": "multi_tool_call", "tools": atomic_tools}
