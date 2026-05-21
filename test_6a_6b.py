import os
import sys
from pathlib import Path

# Add MAYDAY root to path
MAYDAY_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(MAYDAY_ROOT))

from core.orchestrator import Orchestrator
from runtime.engine import ExecutionEngine
from tools.file_tools import FileTools
from runtime.browser_automation import BrowserAutomation
from tools.system_tools import SystemTools
from tools.project_tools import ProjectTools
from tools.powershell_tools import PowerShellTools
from runtime.server_runner import ServerRunner
from core.session import SessionManager
from runtime.api_manager import ApiManager
from runtime.permission_gate import permission_gate

# We need a dummy router that simply returns "respond" to trigger tool_recovery
class DummyRouter:
    def route(self, messages, context=""):
        prompt = messages[-1]["content"] if isinstance(messages, list) else messages
        if "flappy bird" in prompt.lower():
            # Simulate a model returning raw python code instead of JSON
            code = '```python\nprint("Flappy Bird Game!")\n```'
            return f'{{"action": "respond", "text": {repr(code)}}}', "dummy"
        return '{"action": "respond", "text": "I am responding"}', "dummy"

def main():
    print("Initializing Engine...")
    engine = ExecutionEngine()
    powershell_tool = PowerShellTools()
    
    # Register tools EXACTLY as main.py does, EXCEPT we must use BrowserAutomation!
    # Wait, main.py uses BrowserTools(). Let's use BrowserTools to simulate main.py environment accurately.
    from tools.browser_tools import BrowserTools
    # We will register BrowserAutomation first, as it would be if engine registers it internally,
    # and then register BrowserTools, testing our fix in engine.py.
    engine.register_tools({
        "file": FileTools(),
        "browser": BrowserTools(),
        "system": SystemTools(),
        "project": ProjectTools(),
        "powershell": powershell_tool,
        "shell": powershell_tool,
        "server": ServerRunner(),
    })
    
    engine.set_gateway_callback(lambda action, details: "ALLOW")
    
    # Enable auto approve for testing
    os.environ["MAYDAY_AUTO_APPROVE_BROWSER"] = "1"
    
    router = DummyRouter()
    session = SessionManager()
    orchestrator = Orchestrator(router, engine, session)
    
    def on_step(step, msg):
        print(f"Step {step}: {msg}")
        
    def on_tool(name, params):
        print(f"Tool Call: {name}({params})")
        
    def on_resp(text, prov):
        print(f"Final Response: {text}")
        
    orchestrator.set_callbacks(on_step, on_tool, on_resp)
    
    print("\n" + "="*80)
    print("TESTING PHASE 6A: BROWSER AUTOMATION")
    print("="*80)
    prompt_6a = "OPEN browser to google.com and TYPE exactly: MAYDAY validation testing in search bar then CLICK search button"
    result_6a = orchestrator.process_prompt(prompt_6a)
    print("Result 6A:", result_6a)
    
    print("\n" + "="*80)
    print("TESTING PHASE 6B: PYQT6 CALCULATOR")
    print("="*80)
    prompt_6b = r'USE API ONLY MAKE a PyQt6 based calculator app, save inside E:\MAYDAY\projects\pyqt6_calc_real'
    result_6b = orchestrator.process_prompt(prompt_6b)
    print("Result 6B:", result_6b)

    print("\n" + "="*80)
    print("TESTING PHASE 6B: FLAPPY BIRD")
    print("="*80)
    prompt_flappy = r'USE API ONLY MAKE a PyQt6 based flappy bird game and save insidee E:\MAYDAY\projects\flappy_test'
    result_flappy = orchestrator.process_prompt(prompt_flappy)
    print("Result Flappy:", result_flappy)

if __name__ == "__main__":
    main()
