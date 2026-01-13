import os
import subprocess
import sys
import time
import base64
from dotenv import load_dotenv
import autogen
import html
import json
from datetime import datetime
import re
load_dotenv()
import requests

config_list = [{"model": "llama-3.3-70b-versatile", "api_key": os.getenv("GROQ_API_KEY"), "api_type": "groq"}]
os.makedirs("output", exist_ok=True)
os.makedirs("memory", exist_ok=True)


def wait_for_file(filepath, timeout=5):
    """Helper to wait for a file to exist and have content."""
    for _ in range(timeout):
        if os.path.exists(filepath) and os.path.getsize(filepath) > 0:
            return True
        time.sleep(1)
    return False


# ============================================================================
#                           ENHANCED SESSION MEMORY
# ============================================================================

class DiagramMemory:
    """Manages conversation state with optimized context for LLMs"""
    
    def __init__(self, session_id=None):
        self.session_id = session_id or f"session_{int(time.time())}"
        self.memory_file = f"memory/{self.session_id}.json"
        self.max_iterations = 10
        self.state = self._load_or_create()
    
    def _load_or_create(self):
        """Load existing session or create new one"""
        if os.path.exists(self.memory_file):
            with open(self.memory_file, 'r') as f:
                return json.load(f)
        else:
            return {
                "session_id": self.session_id,
                "diagram_type": None,
                "iteration": 0,
                "history": [],
                "current_code": None,
                "component_state": {},  # Track what exists currently
                "base_filename": None,
                "created_at": datetime.now().isoformat()
            }
    
    def save(self):
        """Persist state to disk"""
        with open(self.memory_file, 'w') as f:
            json.dump(self.state, f, indent=2)
    
    def extract_components(self, code, diagram_type):
        """Extract component list from code for tracking"""
        components = set()
        
        if diagram_type == "cloud":
            # Extract Python Diagrams nodes
            matches = re.findall(r'(\w+)\s*=\s*\w+\(', code)
            components.update(matches)
        
        elif diagram_type == "mermaid":
            # Extract Mermaid nodes
            matches = re.findall(r'(\w+)[\[\(].*?[\]\)]', code)
            components.update(matches)
        
        elif diagram_type == "d2":
            # Extract D2 nodes
            matches = re.findall(r'^(\w+):\s*', code, re.MULTILINE)
            components.update(matches)
        
        return list(components)
    
    def add_iteration(self, prompt, code, diagram_type, modifications=None):
        """Add iteration with component tracking"""
        if self.state["iteration"] >= self.max_iterations:
            raise Exception(f"Maximum iterations ({self.max_iterations}) reached. Start a new session.")
        
        self.state["iteration"] += 1
        self.state["diagram_type"] = diagram_type
        self.state["current_code"] = code
        
        # Update component state
        current_components = self.extract_components(code, diagram_type)
        self.state["component_state"] = {comp: True for comp in current_components}
        
        iteration_data = {
            "step": self.state["iteration"],
            "prompt": prompt,
            "components": current_components,
            "modifications": modifications or [],
            "timestamp": datetime.now().isoformat()
        }
        
        self.state["history"].append(iteration_data)
        self.save()
        return self.state["iteration"]
    
    def get_compact_context(self):
        """Generate token-efficient context for LLM"""
        if not self.state["history"]:
            return ""
        
        # Only send last 3 iterations to save tokens
        recent_history = self.state["history"][-3:]
        
        context = f"\n{'='*50}\nSESSION CONTEXT (Step {self.state['iteration']}/{self.max_iterations}):\n{'='*50}\n"
        
        for hist in recent_history:
            context += f"\nStep {hist['step']}: {hist['prompt'][:100]}"  # Truncate prompts
            if hist.get('modifications'):
                context += f"\n  Changes: {', '.join(hist['modifications'][:3])}"  # Limit mods
        
        # Show current components
        if self.state["component_state"]:
            active_components = [k for k, v in self.state["component_state"].items() if v]
            context += f"\n\nCURRENT COMPONENTS: {', '.join(active_components)}"
        
        context += f"\n{'='*50}\n"
        return context
    
    def get_editing_instructions(self, user_request):
        """Generate specific editing instructions"""
        instructions = f"\n{'='*50}\nEDITING INSTRUCTIONS:\n{'='*50}\n"
        instructions += f"User Request: {user_request}\n\n"
        
        # Detect operation type
        request_lower = user_request.lower()
        
        if any(word in request_lower for word in ["remove", "delete", "drop", "exclude"]):
            # Extract what to remove
            components_to_remove = self._extract_target_components(user_request)
            instructions += f"OPERATION: REMOVE\n"
            instructions += f"Target: {', '.join(components_to_remove)}\n"
            instructions += f"Action: Delete ALL references to these components from the code\n"
        
        elif any(word in request_lower for word in ["add", "include", "insert"]):
            instructions += f"OPERATION: ADD\n"
            instructions += f"Action: Add new components while preserving existing ones\n"
        
        elif any(word in request_lower for word in ["replace", "change", "swap"]):
            instructions += f"OPERATION: REPLACE\n"
            instructions += f"Action: Replace specified component with new one\n"
        
        else:
            instructions += f"OPERATION: MODIFY\n"
            instructions += f"Action: Make the requested changes\n"
        
        instructions += f"\nCRITICAL: Base your edits on the CURRENT CODE shown below.\n"
        instructions += f"{'='*50}\n"
        return instructions
    
    def _extract_target_components(self, request):
        """Extract component names from request"""
        # Common cloud resources
        patterns = [
            r'(s3|rds|ec2|lambda|dynamo|vpc|elb|sns|sqs|cloudwatch)',
            r'(\w+)\s+(?:bucket|instance|database|function|table)',
        ]
        
        components = []
        request_lower = request.lower()
        
        for pattern in patterns:
            matches = re.findall(pattern, request_lower)
            components.extend(matches)
        
        return list(set(components))
    
    def is_edit_request(self, prompt):
        """Detect if this is an edit request"""
        edit_keywords = [
            "remove", "delete", "add", "modify", "change", "update", 
            "replace", "edit", "adjust", "move", "without", "exclude",
            "include", "make it", "can you", "instead", "drop","remake","reorder","restructure","rebuild"
        ]
        
        prompt_lower = prompt.lower()
        
        if self.state["history"] and any(kw in prompt_lower for kw in edit_keywords):
            return True
        
        return False
    
    def reset(self):
        """Clear current session"""
        if os.path.exists(self.memory_file):
            os.remove(self.memory_file)
        self.state = self._load_or_create()


current_memory = None

def dot_to_png(dot_path: str, png_path: str):
    """Converts DOT to PNG. Params: dot_path, png_path"""
    try:
        abs_dot = os.path.abspath(dot_path)
        abs_png = os.path.abspath(png_path)
        if not os.path.exists(abs_dot):
            return f"Error: DOT file not found at {abs_dot}"
        subprocess.run(["dot", "-Tpng", abs_dot, "-o", abs_png], check=True)
        return f"SUCCESS: PNG created at {abs_png}"
    except Exception as e:
        return f"Error: {e}"


# ============================================================================
#                           D2 TOOLS
# ============================================================================

def save_d2_code(d2_code: str, output_path: str):
    """Save D2 code to .d2 file"""
    try:
        clean_code = d2_code.strip().replace("```d2", "").replace("```", "")
        if not output_path.endswith(".d2"):
            output_path = output_path + ".d2"

        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(clean_code)
        return f"SUCCESS: D2 code saved at {output_path}"
    except Exception as e:
        return f"Error saving D2 code: {e}"


def d2_to_png(d2_file_path: str, output_png: str):
    """Convert D2 file to PNG"""
    try:
        if not wait_for_file(d2_file_path):
            return f"Error: Source file {d2_file_path} was not found or is empty."
        subprocess.run(["d2", d2_file_path, output_png], check=True)
        return f"SUCCESS: PNG created at {output_png}"
    except Exception as e:
        return f"Error: {str(e)}"


def d2_to_svg(d2_file_path: str, output_svg: str):
    """Convert D2 file to SVG"""
    try:
        subprocess.run(["d2", d2_file_path, output_svg], check=True)
        return f"SUCCESS: SVG created at {output_svg}"
    except Exception as e:
        return f"Error: {str(e)}"


def generate_terrastruct_link(d2_code: str):
    """Generate Terrastruct Play link"""
    try:
        clean_code = d2_code.strip().replace("```d2", "").replace("```", "")
        encoded = base64.urlsafe_b64encode(clean_code.encode()).decode()
        return f"https://play.terrastruct.com/?script={encoded}"
    except Exception as e:
        return None


# ============================================================================
#                           DRAW.IO TOOLS
# ============================================================================

def export_to_drawio(dot_file_path: str):
    """Convert DOT to Draw.io XML"""
    try:
        abs_path = os.path.abspath(dot_file_path)
        output_xml = abs_path.replace(".dot", ".xml")
        
        max_retries = 10
        for i in range(max_retries):
            if os.path.exists(abs_path) and os.path.getsize(abs_path) > 0:
                break
            time.sleep(1)
        else:
            return f"Error: File {dot_file_path} not found or empty after waiting."

        venv_python = sys.executable 
        result = subprocess.run([venv_python, "-m", "graphviz2drawio", abs_path, "-o", output_xml], 
                                capture_output=True, text=True)
        
        if result.returncode != 0:
            return f"Conversion Error: {result.stderr}"
            
        return f"SUCCESS: XML created at {output_xml}"
    except Exception as e:
        return f"Error: {str(e)}"

def run_diagram_py(py_file_path: str):
    """Execute a diagrams python file to generate .dot"""
    try:
        result = subprocess.run(
            [sys.executable, py_file_path],
            capture_output=True,
            text=True
        )
        if result.returncode != 0:
            return f"Execution failed: {result.stderr}"
        return "SUCCESS: Diagram script executed"
    except Exception as e:
        return f"Error executing diagram: {e}"

# ============================================================================
#                           MERMAID TOOLS
# ============================================================================

def export_mermaid_to_drawio(mermaid_code: str, output_path: str):
    """Convert Mermaid to Draw.io XML"""
    try:
        clean_code = mermaid_code.strip().replace("```mermaid", "").replace("```", "")
        escaped_code = html.escape(clean_code).replace('\n', '&#xa;')
        
        xml_content = f"""<mxfile host="app.diagrams.net">
  <diagram id="mermaid-1" name="Page-1">
    <mxGraphModel>
      <root>
        <mxCell id="0" />
        <mxCell id="1" parent="0" />
        <mxCell id="2" value="{escaped_code}" style="shape=mxgraph.mermaid.mermaid;whiteSpace=wrap;html=1;" vertex="1" parent="1">
          <mxGeometry x="20" y="20" width="600" height="400" as="geometry" />
        </mxCell>
      </root>
    </mxGraphModel>
  </diagram>
</mxfile>"""

        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(xml_content)
        return f"SUCCESS: Draw.io XML created at {output_path}"
    except Exception as e:
        return f"Error: {str(e)}"


def mermaid_to_png(mermaid_code: str, output_path: str):
    """Convert Mermaid to PNG"""
    try:
        clean_code = mermaid_code.strip().replace("```mermaid", "").replace("```", "")
        
        if "erDiagram" in clean_code and not clean_code.startswith("erDiagram"):
            clean_code = "erDiagram" + clean_code.split("erDiagram")[-1]
        
        elif not any(k in clean_code for k in ["graph", "flowchart", "sequenceDiagram", "erDiagram", "classDiagram"]):
            clean_code = f"graph TD\n{clean_code}"

        encoded_string = base64.b64encode(clean_code.encode('utf-8')).decode('utf-8')
        url = f"https://mermaid.ink/img/{encoded_string}"
        
        response = requests.get(url, timeout=30)
        if response.status_code == 200:
            with open(output_path, 'wb') as f:
                f.write(response.content)
            return f"SUCCESS: PNG created at {output_path}"
        else:
            return f"Error: Web service status {response.status_code}"
    except Exception as e:
        return f"Error: {str(e)}"


def save_mermaid_code(mermaid_code: str, output_path: str):
    """Save Mermaid code"""
    try:
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(mermaid_code)
        return f"SUCCESS: Mermaid code saved at {output_path}"
    except Exception as e:
        return f"Error saving Mermaid code: {e}"

def save_cloud_code(code: str, path: str):
    """Saves cloud diagram python code. Params: code, path"""
    try:
        if not path.endswith(".py"): path += ".py"
        clean_code = code.strip().replace("```python", "").replace("```", "")
        with open(path, "w", encoding="utf-8") as f:
            f.write(clean_code)
        return f"SUCCESS: Python code saved at {path}"
    except Exception as e:
        return f"Error: {e}"


# ============================================================================
#                           AGENT SETUP (OPTIMIZED)
# ============================================================================

cloud_architect = autogen.AssistantAgent(
    name="Architect",
    llm_config={"config_list": config_list, "timeout": 120},
    system_message="""
You are a Cloud Architecture expert. You follow a strict "Step-by-Step" execution protocol.

CRITICAL FILENAME RULE (MANDATORY):
You MUST set the 'filename' parameter in Diagram() to the exact ID provided (e.g., "output/diagram_123").
Example: with Diagram("Title", filename="output/diagram_123", outformat="dot", show=False):

CRITICAL SYNTAX RULES:
1. NO CLUSTER CONNECTIONS: You CANNOT connect a Cluster object to another node (e.g., 'public_subnet >> ec2' is ILLEGAL). You must connect nodes to nodes (e.g., 'lb >> ec2_public').
2. NO 'Subnet' CLASS: Use 'with Cluster("Subnet Name"):'.
3. FILENAME: Use Diagram(..., filename="output/diagram_123", outformat="dot").

CRITICAL TOOL FORMATTING:
- You MUST use standard JSON tool calls. 
- NEVER use <function=...> tags.
- Use EXACT argument names: 'code' and 'path' for save_cloud_code.


LIBRARY SYNTAX RULES (NO EXCEPTIONS):
1. PLURAL IMPORTS: Use 'from diagrams import Diagram, Cluster, Edge'.
2. NO 'Subnet' CLASS: 'diagrams.aws.network' does NOT have a 'Subnet' class. You MUST use 'Cluster' to represent subnets.
3. GLOBAL CONTEXT: Every resource (VPC, EC2, RDS, etc.) MUST be instantiated INSIDE the 'with Diagram(...):' block.
4. PROVIDER MAPPING:
   - AWS: from diagrams.aws.[category] import [Resource]
   - Azure: from diagrams.azure.[category] import [Resource]
   - GCP: from diagrams.gcp.[category] import [Resource]

STRICT TOOL CHAIN (LINEAR ONLY):
STRICT TOOL CALLING:
When calling dot_to_png, use exactly these arguments:
dot_to_png(dot_path="output/diagram_123.dot", png_path="output/diagram_123.png")
You are FORBIDDEN from calling multiple tools at once. You must wait for "SUCCESS" before suggesting the next tool.
Step 1: Call 'save_cloud_code'. (Stop and wait for SUCCESS).
Step 2: Call 'run_diagram_py'. (Stop and wait for SUCCESS).
Step 3: Call 'dot_to_png'. (Stop and wait for SUCCESS).
Step 4: Call 'export_to_drawio'. (Stop and wait for SUCCESS).
Step 5: Type 'TERMINATE'.

IF 'run_diagram_py' FAILS:
Analyze the Traceback. If it says 'ImportError: cannot import name Subnet', rewrite the code using 'Cluster' for subnets, call 'save_cloud_code' again, and restart the chain.

EDITING MODE:
If "CURRENT CODE" is provided, modify ONLY the specific components requested. If removing a node, you MUST delete every line where that node's variable appears, including connection lines (>> or <<).
"""
)

mermaid_architect = autogen.AssistantAgent(
    name="MermaidArchitect",
    llm_config={"config_list": config_list, "timeout": 120},
    system_message="""You are a Mermaid diagram expert with surgical editing precision.

EDITING MODE:
1. Start with the "CURRENT CODE" provided
2. Apply ONLY the requested change
3. Preserve all other elements
4. Track removals: if something is deleted, keep it deleted

TYPES: flowchart, sequenceDiagram, classDiagram, erDiagram, stateDiagram-v2, gantt, pie

EDITING OPERATIONS:
- REMOVE: Delete node and its connections
- ADD: Insert new node with proper syntax
- MODIFY: Update labels or relationships

WORKFLOW:
1. Generate/Edit code
2. Call save_mermaid_code → wait for SUCCESS
3. Call mermaid_to_png → wait for SUCCESS  
4. Call export_mermaid_to_drawio → wait for SUCCESS
5. List changes made, then TERMINATE

NO markdown backticks in tool parameters!"""
)

d2_architect = autogen.AssistantAgent(
    name="D2Architect",
    llm_config={"config_list": config_list, "timeout": 120},
    system_message="""You are a D2 diagram expert with precise editing capabilities.

D2 SYNTAX:
- Nodes: server: "Web Server"
- Connections: client -> server: "HTTPS"
- Containers: aws: { ec2; s3; rds }
- Styling: server.style.fill: "#ff0000"

EDITING MODE:
1. Use "CURRENT CODE" as base
2. Apply requested changes only
3. Maintain structure and relationships
4. Remove means DELETE completely

WORKFLOW:
1. Generate/Edit D2 code
2. Call save_d2_code → wait
3. Call d2_to_png → wait
4. Call d2_to_svg → wait
5. Mention Terrastruct link, then TERMINATE

Clean D2 syntax only - no markdown backticks in tools!"""
)

user_proxy = autogen.UserProxyAgent(
    name="User_Proxy",
    human_input_mode="NEVER",
    max_consecutive_auto_reply=10,
    is_termination_msg=lambda x: "TERMINATE" in (x.get("content") or ""),
    code_execution_config={"work_dir": ".", "use_docker": False},
)

# Tool registrations
autogen.agentchat.register_function(
    f=export_to_drawio, caller=cloud_architect, executor=user_proxy,
    name="export_to_drawio", description="Converts dot to XML"
)

autogen.agentchat.register_function(
    f=save_mermaid_code, caller=mermaid_architect, executor=user_proxy,
    name="save_mermaid_code", description="Saves Mermaid code"
)

autogen.agentchat.register_function(
    f=mermaid_to_png, caller=mermaid_architect, executor=user_proxy,
    name="mermaid_to_png", description="Converts Mermaid to PNG"
)

autogen.agentchat.register_function(
    f=export_mermaid_to_drawio, caller=mermaid_architect, executor=user_proxy,
    name="export_mermaid_to_drawio", description="Converts Mermaid to Draw.io XML"
)

autogen.agentchat.register_function(
    f=save_d2_code, caller=d2_architect, executor=user_proxy,
    name="save_d2_code", description="Saves D2 code"
)

autogen.agentchat.register_function(
    f=d2_to_png, caller=d2_architect, executor=user_proxy,
    name="d2_to_png", description="Converts D2 to PNG"
)

autogen.agentchat.register_function(
    f=d2_to_svg, caller=d2_architect, executor=user_proxy,
    name="d2_to_svg", description="Converts D2 to SVG"
)
autogen.agentchat.register_function(
    f=run_diagram_py,
    caller=cloud_architect,
    executor=user_proxy,
    name="run_diagram_py",
    description="Executes diagram python file to generate DOT"
)
autogen.agentchat.register_function(
    f=save_cloud_code,
    caller=cloud_architect,
    executor=user_proxy,
    name="save_cloud_code",
    description="Saves code to a path. Args: code (str), path (str)"
)
autogen.agentchat.register_function(
    f=dot_to_png,
    caller=cloud_architect,
    executor=user_proxy,
    name="dot_to_png",
    description="Converts DOT to PNG. Args: dot_path (str), png_path (str)"
)

# ============================================================================
#                           DIAGRAM TYPE DETECTION
# ============================================================================

def detect_diagram_type(prompt: str) -> str:
    """Detect diagram type from prompt"""
    prompt_lower = prompt.lower()
    
    d2_keywords = ["d2", "modern diagram", "declarative", "system architecture"]
    cloud_keywords = ["aws", "azure", "gcp", "cloud", "ec2", "s3", "rds", "lambda", "vpc","vnet","cosmos","lambda","bigquery"]
    mermaid_keywords = ["flowchart", "sequence", "er diagram", "class diagram", "process"]
    
    d2_score = sum(1 for kw in d2_keywords if kw in prompt_lower)
    cloud_score = sum(1 for kw in cloud_keywords if kw in prompt_lower)
    mermaid_score = sum(1 for kw in mermaid_keywords if kw in prompt_lower)
    
    scores = [(d2_score, "d2"), (cloud_score, "cloud"), (mermaid_score, "mermaid")]
    max_score, diagram_type = max(scores, key=lambda x: x[0])
    
    if max_score == 0:
        return "cloud" if prompt.endswith('.tf') else "mermaid"
    
    return diagram_type


# ============================================================================
#                           MAIN GENERATION ENGINE
# ============================================================================

def generate_diagram(prompt_input, session_id=None, is_continuation=False):
    """Main generation with optimized memory"""
    global current_memory
    
    # Initialize memory
    if session_id and os.path.exists(f"memory/{session_id}.json"):
        current_memory = DiagramMemory(session_id)
    else:
        current_memory = DiagramMemory()
    
    # Handle file input
    if os.path.isfile(prompt_input):
        with open(prompt_input, 'r') as f:
            content = f.read()
        final_prompt = f"Visualize this IaC code:\n\n{content}"
        diagram_type = "cloud"
        is_edit = False
    else:
        final_prompt = prompt_input
        is_edit = current_memory.is_edit_request(prompt_input)
        diagram_type = current_memory.state["diagram_type"] if is_edit else detect_diagram_type(prompt_input)
    
    # Generate filename
    if current_memory.state["base_filename"]:
        unique_name = current_memory.state["base_filename"]
    else:
        timestamp = int(time.time())
        unique_name = f"diagram_{timestamp}"
        current_memory.state["base_filename"] = unique_name
    
    # Build optimized message
    if is_edit:
        compact_context = current_memory.get_compact_context()
        editing_instructions = current_memory.get_editing_instructions(final_prompt)
        
        llm_message = f"""{compact_context}

{editing_instructions}

CURRENT CODE (Your starting point):
```
{current_memory.state['current_code']}
```

TASK: Edit the above code to apply: {final_prompt}
Save as: output/{unique_name}

CRITICAL RULES:
1. Start from the CURRENT CODE above
2. Apply ONLY the requested change
3. If removing, delete completely
4. Do NOT regenerate from scratch"""
    else:
        llm_message = f"Create: {final_prompt}\nFilename: output/{unique_name}"
    
    # Log
    print(f"\n{'='*60}")
    print(f"Type: {diagram_type.upper()} | Mode: {'EDIT' if is_edit else 'NEW'}")
    print(f"Iteration: {current_memory.state['iteration'] + 1}/{current_memory.max_iterations}")
    print(f"{'='*60}\n")
    
    terrastruct_link = None
    
    try:
        # Route to agent
        if diagram_type == "cloud":
            user_proxy.initiate_chat(cloud_architect, message=llm_message)
        elif diagram_type == "mermaid":
            user_proxy.initiate_chat(mermaid_architect, message=llm_message)
        elif diagram_type == "d2":
            user_proxy.initiate_chat(d2_architect, message=llm_message)
            d2_file = f"output/{unique_name}.d2"
            if os.path.exists(d2_file):
                with open(d2_file, 'r') as f:
                    terrastruct_link = generate_terrastruct_link(f.read())
        
        dot_file = f"output/{unique_name}.dot"
        wait_for_file(dot_file, timeout=10)
        
        # Extract generated code
        generated_code = ""
        possible_files = [
            f"output/{unique_name}.py", 
            "diagram.py", 
            f"output/{unique_name}.mmd", 
            f"output/{unique_name}.d2"
        ]
        for code_file in possible_files:
            if os.path.exists(code_file):
                with open(code_file, 'r', encoding='utf-8') as f:
                    generated_code = f.read()
                break
        
        # Fallback to prevent NoneType error
        if not generated_code:
            generated_code = "# Code captured from memory\n" + (current_memory.state.get('current_code') or "")

        modifications = ["Intial creation"] if not is_edit else [f"Applied: {final_prompt}"]

        # Update memory with valid string
        current_memory.add_iteration(
            prompt=final_prompt,
            code=generated_code,
            diagram_type=diagram_type,
            modifications=modifications
        )
        
        return {
            "unique_name": unique_name,
            "session_id": current_memory.session_id,
            "iteration": current_memory.state["iteration"],
            "diagram_type": diagram_type,
            "terrastruct_link": terrastruct_link,
            "is_edit": is_edit
        }
        
    except Exception as e:
        print(f"Error: {str(e)}")
        raise


def reset_session(session_id):
    """Clear session memory"""
    memory = DiagramMemory(session_id)
    memory.reset()
    print(f"Session {session_id} reset.")


if __name__ == "__main__":
    # Test
    result1 = generate_diagram("draw a AWS complex architecture with VPC, public and private subnets, EC2 instances, RDS database, S3 bucket, and load balancer.")
    print(f"\nSession ID: {result1['session_id']}")
    
    # Test edit
   # result2 = generate_diagram(
       # "Remove S3 bucket", 
        #session_id=result1['session_id'], 
        #is_continuation=True
    #)
    #print(f"\nEdit completed: Iteration {result2['iteration']}")