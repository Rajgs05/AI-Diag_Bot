import os
import subprocess
import sys
import time
import shutil
from dotenv import load_dotenv
import autogen

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

# -------- AGENT SETUP --------
architect = autogen.AssistantAgent(
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

user_proxy = autogen.UserProxyAgent(
    name="User_Proxy",
    human_input_mode="NEVER",
    max_consecutive_auto_reply=10, # Increased to allow for debugging loops
    is_termination_msg=lambda x: "TERMINATE" in (x.get("content") or ""),
    code_execution_config={"work_dir": ".", "use_docker": False},
)

autogen.agentchat.register_function(
    f=export_to_drawio,
    caller=architect,
    executor=user_proxy,
    name="export_to_drawio",
    description="Converts dot to XML"
)

# -------- ENGINE --------
def generate_diagram(prompt_input):
    if os.path.exists("output"):
        for f in os.listdir("output"):
            os.remove(os.path.join("output", f))

    if os.path.isfile(prompt_input):
        with open(prompt_input, 'r') as f:
            content = f.read()
        final_prompt = f"Visualize this IaC code:\n\n{content}"
    else:
        final_prompt = prompt_input

    timestamp = int(time.time())
    unique_name = f"arch_{timestamp}"
    
    user_proxy.initiate_chat(
        architect,
        message=f"Request: {final_prompt}. Note: Save as 'output/{unique_name}'"
    )
    return unique_name

if __name__ == "__main__":
    generate_diagram("main.tf")