import os
import subprocess
import sys
import time
import base64
import requests
import shutil
from dotenv import load_dotenv
import autogen
import html

load_dotenv()

config_list = [{"model": "llama-3.3-70b-versatile", "api_key": os.getenv("GROQ_API_KEY"), "api_type": "groq"}]
os.makedirs("output", exist_ok=True)

# -------- TOOL: DOT → DRAW.IO XML --------
def export_to_drawio(dot_file_path: str):
    try:
        abs_path = os.path.abspath(dot_file_path)
        output_xml = abs_path.replace(".dot", ".xml")
        
        # Adding a small sleep to ensure OS has finished writing the file
        time.sleep(5) 
        
        if not os.path.exists(abs_path):
            return f"Error: File {dot_file_path} not found. Check if the Python script succeeded."

        venv_python = sys.executable 
        subprocess.run([venv_python, "-m", "graphviz2drawio", abs_path, "-o", output_xml], check=True)
        return f"SUCCESS: XML created at {output_xml}"
    except Exception as e:
        return f"Error: {e}"

# -------- TOOL: Mermaid → DRAW.IO XML --------
def export_mermaid_to_drawio(mermaid_code: str, output_path: str):
    """
    Wraps Mermaid code into a Draw.io compatible XML format with proper escaping.
    """
    try:
        # 1. Clean the code
        clean_code = mermaid_code.strip().replace("```mermaid", "").replace("```", "")
        
        # 2. ESCAPE the code for XML (Fixes the xmlParseEntityRef error)
        # This converts & to &amp;, < to &lt;, etc.
        escaped_code = html.escape(clean_code)
        
        # 3. Insert into the XML template
        xml_content = f"""<mxfile host="Electron" modified="{int(time.time())}" agent="5.0" version="21.0.0">
  <diagram id="mermaid-diagram" name="Page-1">
    <mxGraphModel dx="1000" dy="1000" grid="1" gridSize="10" guides="1" tooltips="1" connect="1" arrows="1" fold="1" page="1" pageScale="1" pageWidth="827" pageHeight="1169" math="0" shadow="0">
      <root>
        <mxCell id="0" />
        <mxCell id="1" parent="0" />
        <mxCell id="2" value="&lt;pre&gt;{escaped_code}&lt;/pre&gt;" style="text;html=1;align=left;verticalAlign=top;spacingLeft=4;spacingBottom=4;overflow=hidden;rotatable=0;points=[[0,0.5],[1,0.5],[0.5,0],[0.5,1]];portConstraint=eastwest;whiteSpace=wrap;rounded=0;sketch=0;glass=0;fillColor=none;strokeColor=none;fontFamily=Helvetica;fontSize=12;fontColor=default;" vertex="1" parent="1">
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
        return f"Error creating Mermaid XML: {e}"

def mermaid_to_png(mermaid_code: str, output_path: str):
    """
    Robust Mermaid to PNG conversion with header correction for ER diagrams.
    """
    import base64
    import requests
    try:
        # 1. Clean up markdown or backticks
        clean_code = mermaid_code.strip().replace("```mermaid", "").replace("```", "")
        
        # 2. Logic to ensure headers are present for specific types like erDiagram
        if "erDiagram" in clean_code and not clean_code.startswith("erDiagram"):
            # Move erDiagram to the very start if it was buried
            clean_code = "erDiagram" + clean_code.split("erDiagram")[-1]
        elif not any(k in clean_code for k in ["graph", "flowchart", "sequenceDiagram", "erDiagram", "classDiagram"]):
            # Fallback for generic flowcharts
            clean_code = f"graph TD\n{clean_code}"

        # 3. Proper URL-safe Base64 encoding
        encoded_string = base64.b64encode(clean_code.encode('utf-8')).decode('utf-8')
        url = f"https://mermaid.ink/img/{encoded_string}"
        
        response = requests.get(url, timeout=30)
        if response.status_code == 200:
            with open(output_path, 'wb') as f:
                f.write(response.content)
            return f"SUCCESS: PNG created at {output_path}"
        else:
            # Provide more detail for the agent to debug
            return f"Error: Web service returned {response.status_code}. Raw code: {clean_code[:50]}..."
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

    STRICT 2-TURN WORKFLOW:
    1. TURN 1: Write the Python code. 
       - Use: with Diagram(..., outformat=["png", "dot"], show=False):
       - DO NOT suggest any tool calls yet. End your message after the code block.
    
    2. TURN 2: Wait for User_Proxy to say 'exitcode: 0'. 
       - ONLY THEN call 'export_to_drawio' on the .dot file.
    
    3. FINAL: List paths, say 'ALL FILES CREATED SUCCESSFULLY', and 'TERMINATE'.
    """
)

# -------- Mermaid Architect AGENT SETUP --------
mermaid_architect = autogen.AssistantAgent(
    name="MermaidArchitect",
    llm_config={"config_list": config_list},
    system_message=
    """You are a Business Process and Software Architecture expert specializing in Mermaid.js.

    You can create these diagram types:
    1. **flowchart** - Business processes, workflows, decision trees
    2. **sequenceDiagram** - API flows, system interactions, user journeys
    3. **classDiagram** - OOP design, software architecture
    4. **erDiagram** - Database schemas, data models
    5. **stateDiagram-v2** - State machines, status workflows
    6. **gantt** - Project timelines, schedules
    7. **pie** - Statistics, distributions
    8. **journey** - User experience flows

    STRICT FILENAME RULES:
    - Save code as .mmd
    - Save image as .png
    - Save Draw.io export as .xml (DO NOT use .drawio)

    STRICT SEQUENTIAL WORKFLOW:
    1. Generate the raw Mermaid code.
    2. Call 'save_mermaid_code'.
    3. Call 'mermaid_to_png'.
    4. Call 'export_mermaid_to_drawio'.
    5. Say 'TERMINATE'.
    """

)



user_proxy = autogen.UserProxyAgent(
    name="User_Proxy",
    human_input_mode="NEVER",
    max_consecutive_auto_reply=10, # Increased to allow for debugging loops
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
    description="Converts Mermaid code to PNG image using web service"
)

autogen.agentchat.register_function(
    f=export_mermaid_to_drawio,
    caller=mermaid_architect,
    executor=user_proxy,
    name="export_mermaid_to_drawio",
    description="Converts Mermaid code to Draw.io XML format"
)



def detect_diagram_type(prompt: str) -> str:
    """
    Detect what type of diagram the user wants based on keywords
    
    Returns: "cloud" or "mermaid"
    """
    prompt_lower = prompt.lower()
    
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
    
    # Check for cloud keywords
    cloud_score = sum(1 for keyword in cloud_keywords if keyword in prompt_lower)
    
    # Check for mermaid keywords
    mermaid_score = sum(1 for keyword in mermaid_keywords if keyword in prompt_lower)
    
    # Decision logic
    if cloud_score > mermaid_score:
        return "cloud"
    elif mermaid_score > cloud_score:
        return "mermaid"
    else:
        # Default: if ambiguous, check for file extension
        if prompt.endswith('.tf'):
            return "cloud"
        # Default to mermaid for general business diagrams
        return "mermaid"
    




# -------- MAIN GENERATION ENGINE --------
def generate_diagram(prompt_input):
    """
    Main function to generate diagrams (cloud or mermaid)
    
    Args:
        prompt_input: Either text prompt or file path
    
    Returns:
        unique_name: Base filename for generated files
    """
    # Clear output directory
    if os.path.exists("output"):
        for f in os.listdir("output"):
            os.remove(os.path.join("output", f))

    # Handle file input
    if os.path.isfile(prompt_input):
        with open(prompt_input, 'r') as f:
            content = f.read()
        final_prompt = f"Visualize this IaC code:\n\n{content}"
        diagram_type = "cloud"  # File input is always cloud architecture
    else:
        final_prompt = prompt_input
        diagram_type = detect_diagram_type(prompt_input)

    # Generate unique filename
    timestamp = int(time.time())
    unique_name = f"diagram_{timestamp}"
    
    # Route to appropriate agent
    if diagram_type == "cloud":
        print(f" Detected: Cloud Architecture Diagram")
        user_proxy.initiate_chat(
            cloud_architect,
            message=f"Request: {final_prompt}. Note: Save as 'output/{unique_name}'"
        )
    else:
        print(f" Detected: Mermaid Business Diagram")
        user_proxy.initiate_chat(
            mermaid_architect,
            message=f"""Request: {final_prompt}
            
            You MUST follow this exact sequence:
            1. Call save_mermaid_code with 'output/{unique_name}.mmd'
            2. Call mermaid_to_png with 'output/{unique_name}.png'
            3. Call export_mermaid_to_drawio with 'output/{unique_name}.xml'
            """
        )
    
    return unique_name








if __name__ == "__main__":
    generate_diagram("Create an ER diagram for loan approval system with Customers, Loans, Payments.")  # Test run