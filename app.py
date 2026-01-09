import streamlit as st
import os
import time
import urllib.parse
import json
from main import generate_diagram, reset_session

st.set_page_config(page_title="Diagram Bot Pro", layout="wide")

# Initialize session state
if 'current_session_id' not in st.session_state:
    st.session_state.current_session_id = None
if 'iteration_count' not in st.session_state:
    st.session_state.iteration_count = 0
if 'diagram_type' not in st.session_state:
    st.session_state.diagram_type = None
if 'chat_history' not in st.session_state:
    st.session_state.chat_history = []

# ============================================================================
#                           HEADER
# ============================================================================

st.title("Diagram Bot")
st.markdown("Generate & Iteratively Edit Professional Diagrams using AI")

# Iteration counter in header
if st.session_state.iteration_count > 0:
    st.info(f" **Active Session** | Iteration: {st.session_state.iteration_count}/10 | Type: {st.session_state.diagram_type or 'N/A'}")

# ============================================================================
#                           SIDEBAR
# ============================================================================

with st.sidebar:
    st.header(" Session Control")
    
    # Session info
    if st.session_state.current_session_id:
        st.success(f"**Session Active**")
        st.caption(f"ID: {st.session_state.current_session_id[:12]}...")
        
        # Reset button
        if st.button(" Start New Session", type="secondary"):
            st.session_state.current_session_id = None
            st.session_state.iteration_count = 0
            st.session_state.diagram_type = None
            st.session_state.chat_history = []
            st.rerun()
    else:
        st.info("No active session")
    
    st.markdown("---")
    
    # Chat history
    st.header(" Conversation History")
    if st.session_state.chat_history:
        for i, entry in enumerate(st.session_state.chat_history, 1):
            with st.expander(f"Step {i}: {entry['action']}", expanded=(i == len(st.session_state.chat_history))):
                st.caption(entry['prompt'][:100] + "..." if len(entry['prompt']) > 100 else entry['prompt'])
                st.caption(f"Time: {entry['timestamp']}")
    else:
        st.caption("No history yet")
    
    st.markdown("---")
    
    # Project files
    st.header(" Project Files")
    if os.path.exists("output"):
        files = sorted(os.listdir("output"), reverse=True)
        if files:
            for f in files[:10]:  # Show last 10 files
                st.text(f" {f}")
        else:
            st.caption("No files yet")
    
    if st.button("🗑️ Clear All Output"):
        if os.path.exists("output"):
            for f in os.listdir("output"):
                os.remove(os.path.join("output", f))
            st.success("Cleared!")
            st.rerun()
    
    st.markdown("---")
    
    # Help section
    with st.expander("ℹ️ Help & Examples"):
        st.markdown("""
        **Diagram Types:**
        - **Cloud**: AWS, Azure, GCP architectures
        - **Mermaid**: Flowcharts, ER diagrams, sequences
        - **D2**: Modern declarative diagrams
        
        **Iterative Editing:**
        1. Create initial diagram
        2. Use prompts like:
           - "Remove the S3 bucket"
           - "Add a Lambda function"
           - "Change RDS to DynamoDB"
        3. Edit up to 10 times per session
        
        **Example Prompts:**
        - "Draw AWS with EC2, S3, RDS"
        - "Create a flowchart for login"
        - "Make an ER diagram for e-commerce"
        """)

# ============================================================================
#                           MAIN INPUT AREA
# ============================================================================

st.markdown("---")

col_input, col_upload = st.columns([3, 1])

with col_input:
    # Contextual placeholder
    if st.session_state.iteration_count > 0:
        placeholder_text = "Enter your edit request (e.g., 'remove S3 bucket', 'add Lambda function')"
    else:
        placeholder_text = "Describe the diagram you want (e.g., 'AWS architecture with EC2, S3, RDS')"
    
    prompt = st.text_area(
        "Your Request",
        placeholder=placeholder_text,
        height=120,
        key="main_prompt"
    )

with col_upload:
    st.markdown("**Or Upload**")
    uploaded_file = st.file_uploader(
        "Terraform File",
        type=["tf"],
        help="Upload .tf file for cloud architecture"
    )

# Determine input
final_input = None
if uploaded_file is not None:
    os.makedirs("output", exist_ok=True)
    temp_file_path = os.path.join("output", uploaded_file.name)
    with open(temp_file_path, "wb") as f:
        f.write(uploaded_file.getbuffer())
    final_input = temp_file_path
    st.info(f"📎 Using: **{uploaded_file.name}**")
elif prompt:
    final_input = prompt

# ============================================================================
#                           GENERATION BUTTON
# ============================================================================

# Button text based on state
if st.session_state.iteration_count > 0:
    button_text = f" Apply Edit (Step {st.session_state.iteration_count + 1}/10)"
    button_type = "secondary"
else:
    button_text = " Generate Diagram"
    button_type = "primary"

if st.button(button_text, type=button_type, use_container_width=True):
    if final_input:
        # Check iteration limit
        if st.session_state.iteration_count >= 10:
            st.error(" Maximum iterations (10) reached. Please start a new session.")
        else:
            with st.spinner(" AI is working..."):
                try:
                    # Call generation engine
                    result = generate_diagram(
                        final_input,
                        session_id=st.session_state.current_session_id,
                        is_continuation=(st.session_state.iteration_count > 0)
                    )
                    
                    # Update session state
                    st.session_state.current_session_id = result["session_id"]
                    st.session_state.iteration_count = result["iteration"]
                    st.session_state.diagram_type = result["diagram_type"]
                    
                    # Add to history
                    st.session_state.chat_history.append({
                        "action": "Edit" if result["is_edit"] else "Create",
                        "prompt": final_input if isinstance(final_input, str) else f"File: {uploaded_file.name}",
                        "timestamp": time.strftime("%H:%M:%S")
                    })
                    
                    # File paths
                    unique_name = result["unique_name"]
                    png_path = f"output/{unique_name}.png"
                    xml_path = f"output/{unique_name}.xml"
                    svg_path = f"output/{unique_name}.svg"
                    
                    time.sleep(2)  # File sync
                    
                    # ============================================================================
                    #                           RESULTS DISPLAY
                    # ============================================================================
                    
                    if os.path.exists(png_path):
                        st.success(" Generation Complete!")
                        
                        col_res1, col_res2 = st.columns([2, 1])
                        
                        with col_res1:
                            st.subheader(" Visual Diagram")
                            st.image(png_path, use_container_width=True)
                        
                        with col_res2:
                            st.subheader(" Downloads & Edit")
                            
                            # Edit button based on type
                            if result["diagram_type"] == "d2":
                                # D2 diagrams: Terrastruct link
                                if result["terrastruct_link"]:
                                    st.markdown(f"""
                                        <a href="{result['terrastruct_link']}" target="_blank">
                                            <button style="
                                                width: 100%;
                                                background-color: #4CAF50;
                                                color: white;
                                                padding: 12px;
                                                border: none;
                                                border-radius: 8px;
                                                cursor: pointer;
                                                font-size: 16px;
                                                font-weight: bold;
                                                margin-bottom: 10px;">
                                                🎨 Edit in Terrastruct
                                            </button>
                                        </a>
                                    """, unsafe_allow_html=True)
                                    st.caption("D2 diagrams open in Terrastruct Play")
                                
                                # SVG download for D2
                                if os.path.exists(svg_path):
                                    with open(svg_path, "rb") as f:
                                        st.download_button(
                                            label=" Download SVG",
                                            data=f,
                                            file_name=f"{unique_name}.svg",
                                            mime="image/svg+xml"
                                        )
                            
                            else:
                                # Cloud/Mermaid: Draw.io link
                                if os.path.exists(xml_path):
                                    with open(xml_path, "r", encoding="utf-8") as f:
                                        xml_data = f.read()
                                    
                                    encoded_xml = urllib.parse.quote(xml_data)
                                    drawio_url = f"https://app.diagrams.net/#R{encoded_xml}"
                                    
                                    st.markdown(f"""
                                        <a href="{drawio_url}" target="_blank">
                                            <button style="
                                                width: 100%;
                                                background-color: #ff4b4b;
                                                color: white;
                                                padding: 12px;
                                                border: none;
                                                border-radius: 8px;
                                                cursor: pointer;
                                                font-size: 16px;
                                                font-weight: bold;
                                                margin-bottom: 10px;">
                                                ✏️ Edit in Draw.io
                                            </button>
                                        </a>
                                    """, unsafe_allow_html=True)
                            
                            st.markdown("---")
                            
                            # Dynamic download buttons
                            extensions = {
                                ".png": ("Download PNG", "image/png"),
                                ".xml": ("Download XML", "application/xml"),
                                ".dot": ("Download DOT", "text/plain"),
                                ".mmd": ("Download Mermaid", "text/plain"),
                                ".d2": ("Download D2", "text/plain"),
                                ".svg": ("Download SVG", "image/svg+xml")
                            }
                            
                            for ext, (label, mime) in extensions.items():
                                file_path = f"output/{unique_name}{ext}"
                                if os.path.exists(file_path):
                                    with open(file_path, "rb") as f:
                                        st.download_button(
                                            label=label,
                                            data=f,
                                            file_name=f"{unique_name}{ext}",
                                            mime=mime,
                                            key=f"btn_{unique_name}_{ext}"
                                        )
                            
                            st.markdown("---")
                            
                            # Iteration tip
                            if st.session_state.iteration_count < 10:
                                st.info(f"💡 **Tip:** You can make {10 - st.session_state.iteration_count} more edits to this diagram!")
                    
                    else:
                        st.error(" PNG not found. Check logs for errors.")
                
                except Exception as e:
                    st.error(f" Error: {str(e)}")
                    import traceback
                    st.code(traceback.format_exc())
    
    else:
        st.warning(" Please enter a prompt or upload a file first.")

# ============================================================================
#                           FOOTER
# ============================================================================

st.markdown("---")
st.markdown("""
<div style='text-align: center; color: #666; padding: 20px;'>
    <p><strong>Diagram Bot Pro</strong> | Supports: Cloud (Diagrams) | Mermaid | D2</p>
    <p>Powered by AutoGen + Groq LLama 3.3 | Iterative editing with memory</p>
</div>
""", unsafe_allow_html=True)