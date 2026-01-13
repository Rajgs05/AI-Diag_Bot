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
    return False  # <--- Change 'Fal' to 'False' here
# Session Memory
class DiagramMemory:
    """Manages conversation state and diagram history for iterative editing"""
    
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
                "components": [],
                "base_filename": None,
                "created_at": datetime.now().isoformat()
            }
    
    def save(self):
        """Persist state to disk"""
        with open(self.memory_file, 'w') as f:
            json.dump(self.state, f, indent=2)
    
    def add_iteration(self, prompt, code, diagram_type, modifications=None):
        """Add a new iteration to history"""
        if self.state["iteration"] >= self.max_iterations:
            raise Exception(f"Maximum iterations ({self.max_iterations}) reached. Start a new session.")
        
        self.state["iteration"] += 1
        self.state["diagram_type"] = diagram_type
        self.state["current_code"] = code
        
        iteration_data = {
            "step": self.state["iteration"],
            "prompt": prompt,
            "code": code,
            "modifications": modifications or [],
            "timestamp": datetime.now().isoformat()
        }
        
        self.state["history"].append(iteration_data)
        self.save()
        return self.state["iteration"]
    
    def get_context_for_llm(self):
        """Generate context string for LLM about previous iterations"""
        if not self.state["history"]:
            return ""
        
        # INCREASED from [-3:] to [-10:] to track all 10 steps
        context = f"\n{'='*60}\nFULL SESSION HISTORY (Iteration {self.state['iteration']}/{self.max_iterations}):\n{'='*60}\n"
        
        for hist in self.state["history"][-10:]:  
            context += f"\nStep {hist['step']}: {hist['prompt']}"
            if hist['modifications']:
                context += f"\n  Action: {', '.join(hist['modifications'])}"
        
        context += f"\n\nCRITICAL: The code below is the CURRENT state. DO NOT re-add items previously removed.\nCURRENT CODE:\n{self.state['current_code']}\n{'='*60}\n"
        return context
    
    def is_edit_request(self, prompt):
        """Detect if this is an edit request vs new diagram"""
        edit_keywords = [
            "remove", "delete", "add", "modify", "change", "update", 
            "replace", "edit", "adjust", "move", "without", "exclude",
            "include", "make it", "can you", "instead"
        ]
        
        prompt_lower = prompt.lower()
        
        # If we have history and prompt contains edit keywords
        if self.state["history"] and any(kw in prompt_lower for kw in edit_keywords):
            return True
        
        return False
    
    def reset(self):
        """Clear current session"""
        if os.path.exists(self.memory_file):
            os.remove(self.memory_file)
        self.state = self._load_or_create()


# Global memory instance (will be set per session)
current_memory = None


#D2 Tool
def save_d2_code(d2_code: str, output_path: str):
    """Save D2 code to .d2 file"""
    try:
        clean_code = d2_code.strip().replace("```d2", "").replace("```", "")
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(clean_code)
        return f"SUCCESS: D2 code saved at {output_path}"
    except Exception as e:
        return f"Error saving D2 code: {e}"


def d2_to_png(d2_file_path: str, output_png: str):
    """Convert D2 file to PNG using d2 CLI with safety check"""
    try:
        # Wait for the .d2 file to exist before compiling
        if not wait_for_file(d2_file_path):
            return f"Error: Source file {d2_file_path} was not found or is empty."
            
        subprocess.run(["d2", d2_file_path, output_png], check=True)
        return f"SUCCESS: PNG created at {output_png}"
    except Exception as e:
        return f"Error: {str(e)}"

def d2_to_svg(d2_file_path: str, output_svg: str):
    """Convert D2 file to SVG (better for editing)"""
    try:
        subprocess.run(["d2", d2_file_path, output_svg], check=True)
        return f"SUCCESS: SVG created at {output_svg}"
    except Exception as e:
        return f"Error: {str(e)}"


def generate_terrastruct_link(d2_code: str):
    """Generate Terrastruct Play link for editing D2 diagrams"""
    try:
        clean_code = d2_code.strip().replace("```d2", "").replace("```", "")
        encoded = base64.urlsafe_b64encode(clean_code.encode()).decode()
        return f"https://play.terrastruct.com/?script={encoded}"
    except Exception as e:
        return None







# -------- TOOL: DOT → DRAW.IO XML --------
def export_to_drawio(dot_file_path: str):
    """Convert DOT to Draw.io XML with retry logic to wait for file creation"""
    try:
        abs_path = os.path.abspath(dot_file_path)
        output_xml = abs_path.replace(".dot", ".xml")
        
        # Adding a small sleep to ensure OS has finished writing the file
        max_retries = 10
        for i in range(max_retries):
            if os.path.exists(abs_path) and os.path.getsize(abs_path) > 0:
                break
            time.sleep(1)
        else:
            return f"Error: File {dot_file_path} not found or empty after waiting. Ensure the Diagram code executed correctly."

        venv_python = sys.executable 
        # Use -m to ensure it uses the library installed in your venv
        result = subprocess.run([venv_python, "-m", "graphviz2drawio", abs_path, "-o", output_xml], 
                                capture_output=True, text=True)
        
        if result.returncode != 0:
            return f"Conversion Error: {result.stderr}"
            
        return f"SUCCESS: XML created at {output_xml}"
    except Exception as e:
        return f"Error: {str(e)}"
        
# -------- TOOL: Mermaid → DRAW.IO XML --------
def export_mermaid_to_drawio(mermaid_code: str, output_path: str):
    try:
        # 1. Clean code and remove problematic newlines for the XML attribute
        clean_code = mermaid_code.strip().replace("```mermaid", "").replace("```", "")
        # Replace actual newlines with XML entity representation to prevent tool failures
        escaped_code = html.escape(clean_code).replace('\n', '&#xa;')
        
        # 2. Use the 'shape=mxgraph.mermaid.mermaid' style which draw.io recognizes
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
    """
    Convert Mermaid code to PNG using web service.
    """
    import base64
    import requests
    try:
        # 1. Aggressively clean the code
        clean_code = mermaid_code.strip().replace("```mermaid", "").replace("```", "")
        
        # 2. Fix ER Diagram headers if buried
        if "erDiagram" in clean_code and not clean_code.startswith("erDiagram"):
            clean_code = "erDiagram" + clean_code.split("erDiagram")[-1]
        
        # 3. Add default header if missing entirely
        elif not any(k in clean_code for k in ["graph", "flowchart", "sequenceDiagram", "erDiagram", "classDiagram"]):
            clean_code = f"graph TD\n{clean_code}"

        # 4. Encoding for the web service
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
    """Save Mermaid code to .mmd file"""
    try:
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(mermaid_code)
        return f"SUCCESS: Mermaid code saved at {output_path}"
    except Exception as e:
        return f"Error saving Mermaid code: {e}"




# -------- Cloud Architect AGENT SETUP --------
cloud_architect = autogen.AssistantAgent(
    name="Architect",
    llm_config={"config_list": config_list},
    system_message="""You are a Senior Cloud Architect. 
    
    IMPORT RULES:
    - AWS Cloudwatch is: from diagrams.aws.management import Cloudwatch (lowercase 'w').
    - Always use: from diagrams import Diagram, Edge, Cluster.
    
    STRICT OPERATIONAL RULES:
    1. Provide your Python code in a block. You MUST use 'output/{unique_name}' for the filename.
    2. STOP and wait for the User_Proxy to execute the code and return 'exitcode: 0'.
    3. ONLY AFTER exitcode 0, call 'export_to_drawio(dot_file_path="output/{unique_name}.dot")'.
    4. NEVER call the tool in the same message as the code.

    MEMORY RULES:
    - Use the 'CURRENT CODE' as the only source of truth.
    - If a component was removed in a previous step, it MUST NOT appear in your new code.
    - Build your new code by modifying the 'CURRENT CODE' directly.
    
    ITERATIVE MEMORY RULES:
    - Modify the 'CURRENT CODE' provided in the context.
    - If a user asked to remove a component in a previous step, DO NOT add it back.
    - Example-If you are removing 's3', delete all references to 'S3' and its edges from the code.

    WORKFLOW:
    Step 1: Write and EXECUTE the Python code.
    Step 2: Wait for exitcode 0.
    Step 3: Call export_to_drawio(dot_file_path='output/{unique_name}.dot').
    Step 4: Say TERMINATE."""
)

# -------- Mermaid Architect AGENT SETUP --------
mermaid_architect = autogen.AssistantAgent(
    name="MermaidArchitect",
    llm_config={"config_list": config_list},
    system_message=
    """You are a Business Process expert with iterative editing capabilities.
    ITERATIVE EDITING MODE:
    When you receive CONVERSATION CONTEXT:
    1. Analyze the CURRENT CODE (Mermaid syntax)
    2. Parse the modification request
    3. Edit the diagram code:
    - Remove: Delete nodes and their connections
    - Add: Insert new nodes with proper syntax
    - Modify: Update labels, styles, or relationships
    4. Preserve diagram type and overall flow

    SUPPORTED TYPES: flowchart, sequenceDiagram, classDiagram, erDiagram, stateDiagram-v2, gantt, pie, journey

    WORKFLOW:
    1. Generate/Edit Mermaid code
    2. Call 'save_mermaid_code' → wait for SUCCESS
    3. Call 'mermaid_to_png' → wait for SUCCESS
    4. Call 'export_mermaid_to_drawio' → wait for SUCCESS
    5. Mention changes made, then 'TERMINATE'

    CRITICAL: 
    - No markdown backticks in tool parameters
    - Execute tools sequentially
    - Track modifications
    """
)

#D2 Architect AGENT SETUP
d2_architect = autogen.AssistantAgent(
    name="D2Architect",
    llm_config={"config_list": config_list},
    system_message="""You are a D2 Diagramming expert specializing in declarative diagrams.

D2 is a modern diagram scripting language. You can create:
- System architectures
- Network diagrams
- Database schemas
- Sequence diagrams
- Component relationships

D2 SYNTAX BASICS:
- Nodes: server: "Web Server"
- Connections: client -> server: "HTTPS"
- Containers: aws: { ec2; s3; rds }
- Styling: server.style.fill: "#ff0000"

ITERATIVE EDITING MODE:
When you receive CONVERSATION CONTEXT:
1. Analyze the CURRENT CODE (D2 syntax)
2. Parse modifications
3. Edit intelligently:
   - Remove: Delete node definitions and connections
   - Add: Insert new nodes with proper D2 syntax
   - Modify: Update labels, styles, or connections
4. Maintain structure and relationships

WORKFLOW:
1. Generate/Edit D2 code
2. Call 'save_d2_code' → wait for SUCCESS
3. Call 'd2_to_png' → wait for SUCCESS
4. Call 'd2_to_svg' → wait for SUCCESS
5. List changes, mention Terrastruct link for editing, then 'TERMINATE'

CRITICAL:
- Use clean D2 syntax (no markdown backticks in tool calls)
- Execute tools sequentially
- D2 diagrams are edited at: https://play.terrastruct.com/
"""
)







user_proxy = autogen.UserProxyAgent(
    name="User_Proxy",
    human_input_mode="NEVER",
    max_consecutive_auto_reply=15, # Increased to allow for debugging loops
    is_termination_msg=lambda x: "TERMINATE" in (x.get("content") or ""),
    code_execution_config={"work_dir": ".", "use_docker": False},
)



# Cloud Architect tool registration
autogen.agentchat.register_function(
    f=export_to_drawio,
    caller=cloud_architect,
    executor=user_proxy,
    name="export_to_drawio",
    description="Converts dot to XML"
)

# Mermaid Architect tool registration
autogen.agentchat.register_function(
    f=save_mermaid_code,
    caller=mermaid_architect,
    executor=user_proxy,
    name="save_mermaid_code",
    description="Saves Mermaid diagram code to .mmd file"
)

autogen.agentchat.register_function(
    f=mermaid_to_png,
    caller=mermaid_architect,
    executor=user_proxy,
    name="mermaid_to_png",
    description="Converts Mermaid code to PNG image"
)

autogen.agentchat.register_function(
    f=export_mermaid_to_drawio,
    caller=mermaid_architect,
    executor=user_proxy,
    name="export_mermaid_to_drawio",
    description="Converts Mermaid code to Draw.io XML format"
)

# D2 Architect tools
autogen.agentchat.register_function(
    f=save_d2_code,
    caller=d2_architect,
    executor=user_proxy,
    name="save_d2_code",
    description="Saves D2 code to .d2 file"
)

autogen.agentchat.register_function(
    f=d2_to_png,
    caller=d2_architect,
    executor=user_proxy,
    name="d2_to_png",
    description="Converts D2 to PNG using CLI"
)

autogen.agentchat.register_function(
    f=d2_to_svg,
    caller=d2_architect,
    executor=user_proxy,
    name="d2_to_svg",
    description="Converts D2 to SVG for editing"
)



def detect_diagram_type(prompt: str) -> str:
    """
    Detect what type of diagram the user wants based on keywords
    
    Returns: "cloud" or "mermaid"
    """
    prompt_lower = prompt.lower()
    
    #d2 keywords
    d2_keywords = [
        "d2", "modern diagram", "declarative", "system architecture",
        "component diagram", "clean diagram"
    ]


    # Cloud architecture keywords
    cloud_keywords = [
        "aws", "azure", "gcp", "cloud", "infrastructure", "ec2", "s3", "rds",
        "lambda", "vpc", "load balancer", "kubernetes", "k8s", "docker",
        "terraform", "cloudformation", "iac"
    ]
    
    # Mermaid diagram keywords
    mermaid_keywords = [
        "flowchart", "flow chart", "process", "workflow", "sequence",
        "class diagram", "er diagram", "database schema", "state diagram",
        "gantt", "timeline", "project plan", "user journey", "api flow",
        "business process", "decision tree", "oop", "uml"
    ]
    
    # Check for d2 keywords first
    d2_score = sum(1 for keyword in d2_keywords if keyword in prompt_lower)

    # Check for cloud keywords
    cloud_score = sum(1 for keyword in cloud_keywords if keyword in prompt_lower)
    
    # Check for mermaid keywords
    mermaid_score = sum(1 for keyword in mermaid_keywords if keyword in prompt_lower)
    
    # Decide
    scores = [
        (d2_score, "d2"),
        (cloud_score, "cloud"),
        (mermaid_score, "mermaid")
    ]
    
    max_score, diagram_type = max(scores, key=lambda x: x[0])
    
    # Default logic
    if max_score == 0:
        if prompt.endswith('.tf'):
            return "cloud"
        return "mermaid"  # Default
    
    return diagram_type
    




# -------- MAIN GENERATION ENGINE --------
def generate_diagram(prompt_input, session_id=None, is_continuation=False):
    """
    Main generation function with memory support
    
    Args:
        prompt_input: Text prompt or file path
        session_id: Optional session ID for continuing conversations
        is_continuation: Whether this is an edit request
    
    Returns:
        dict with: unique_name, session_id, iteration, diagram_type, terrastruct_link
    """
    global current_memory
    
    # Initialize or load memory
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
        
        # Determine diagram type
        if is_edit:
            diagram_type = current_memory.state["diagram_type"]
        else:
            diagram_type = detect_diagram_type(prompt_input)
    
    # Generate filename
    if current_memory.state["base_filename"]:
        unique_name = current_memory.state["base_filename"]
    else:
        timestamp = int(time.time())
        unique_name = f"diagram_{timestamp}"
        current_memory.state["base_filename"] = unique_name
    
    # Build message with context for LLM
    context = current_memory.get_context_for_llm() if is_edit else ""
    
    if is_edit:
        llm_message = f"""{context}

USER REQUEST: {final_prompt}

STRICT TASK:
1. Modify the 'CURRENT CODE' provided in the context.
2. If the user asks to remove something, ensure it stays gone.
3. DO NOT revert to any previous version of the code or re-add components if they where removed .
4. Apply ONLY the new change: {final_prompt}
5. Use the same filename: output/{unique_name}
"""
    else:
        llm_message = f"Request: {final_prompt}. Save as 'output/{unique_name}'"
    
    # Route to appropriate agent
    print(f"\n{'='*60}")
    print(f"Diagram Type: {diagram_type.upper()}")
    print(f"Mode: {'EDIT' if is_edit else 'NEW'}")
    print(f"Iteration: {current_memory.state['iteration'] + 1}/{current_memory.max_iterations}")
    print(f"Session ID: {current_memory.session_id}")
    print(f"{'='*60}\n")
    
    terrastruct_link = None
    
    try:
        if diagram_type == "cloud":
            user_proxy.initiate_chat(cloud_architect, message=llm_message)
            
        elif diagram_type == "mermaid":
            user_proxy.initiate_chat(mermaid_architect, message=llm_message)
            
        elif diagram_type == "d2":
            user_proxy.initiate_chat(d2_architect, message=llm_message)
            
            # Generate Terrastruct link if D2 code exists
            d2_file = f"output/{unique_name}.d2"
            if os.path.exists(d2_file):
                with open(d2_file, 'r') as f:
                    d2_code = f.read()
                terrastruct_link = generate_terrastruct_link(d2_code)
        
        time.sleep(5)  # Allow time for file writes
        # Extract code from last generated file
        generated_code = None
        for ext in ['.py', '.mmd', '.d2']:
            code_file = f"output/{unique_name}{ext}"
            if os.path.exists(code_file):
                with open(code_file, 'r') as f:
                    generated_code = f.read()
                break
        
        # Update memory
        modifications = ["Initial creation"] if not is_edit else [f"Modified based on: {final_prompt}"]
        current_memory.add_iteration(
            prompt=final_prompt,
            code=generated_code or "Code not captured",
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
    """Clear a specific session's memory"""
    memory = DiagramMemory(session_id)
    memory.reset()
    print(f"Session {session_id} has been reset.")








if __name__ == "__main__":
    generate_diagram("draw a azure complex architecture for how database of azure is designed.")  # Test run