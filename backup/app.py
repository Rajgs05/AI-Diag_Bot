import streamlit as st
import os
import time
import urllib.parse  # Required for encoding XML data into a URL
from main import generate_diagram

st.set_page_config(page_title="AI Cloud Architect", layout="wide")

st.title("Cloud Architect Bot")
st.markdown("Generate professional Cloud diagrams.")

# Sidebar for history and status
with st.sidebar:
    st.header("Project Files")
    if os.path.exists("output"):
        files = sorted(os.listdir("output"), reverse=True) 
        for f in files:
            st.text(f"📄 {f}")
    
    st.markdown("---")
    if st.button("🗑️ Clear All Output"):
        if os.path.exists("output"):
            for f in os.listdir("output"):
                os.remove(os.path.join("output", f))
            st.success("Output directory cleared!")
            st.rerun()

# --- INPUT SECTION ---
col_input, col_upload = st.columns(2)

with col_input:
    prompt = st.text_area(" Enter Architecture Prompt", 
                         placeholder="e.g., Draw an AWS architecture with an EKS cluster, RDS instance, and S3 bucket.")

with col_upload:
    uploaded_file = st.file_uploader(" Upload Terraform File", type=["tf"])

# Determine final input
final_input = None
if uploaded_file is not None:
    os.makedirs("output", exist_ok=True)
    temp_file_path = os.path.join("output", uploaded_file.name)
    with open(temp_file_path, "wb") as f:
        f.write(uploaded_file.getbuffer())
    final_input = temp_file_path
    st.info(f" Using uploaded file: **{uploaded_file.name}**")
elif prompt:
    final_input = prompt

# --- GENERATION LOGIC ---
if st.button(" Generate Architecture"):
    if final_input:
        with st.spinner("The Architect is analyzing and drawing..."):
            try:
                unique_name = generate_diagram(final_input)
                png_path = f"output/{unique_name}.png"
                xml_path = f"output/{unique_name}.xml"
                
                time.sleep(1) # Ensure file system sync

                if os.path.exists(png_path):
                    st.success(" Generation Complete!")
                    col_res1, col_res2 = st.columns([2, 1])
                    
                    with col_res1:
                        st.subheader(" Visual Diagram")
                        st.image(png_path, use_container_width=True)

                    with col_res2:
                        st.subheader(" Downloads & Edit")
                        
                        # Direct Edit Logic
                        if os.path.exists(xml_path):
                            with open(xml_path, "r", encoding="utf-8") as f:
                                xml_data = f.read()
                            
                            # Encode XML for the Draw.io URL
                            encoded_xml = urllib.parse.quote(xml_data)
                            # The #R parameter tells Draw.io to load the following data
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
                                        margin-bottom: 20px;">
                                         Open & Edit in Draw.io
                                    </button>
                                </a>
                            """, unsafe_allow_html=True)

                        # Standard Download Buttons
                        for ext in [".png", ".dot", ".xml"]:
                            file_path = f"output/{unique_name}{ext}"
                            if os.path.exists(file_path):
                                with open(file_path, "rb") as f:
                                    st.download_button(
                                        label=f"Download {ext.upper()}",
                                        data=f,
                                        file_name=f"{unique_name}{ext}",
                                        mime="application/octet-stream",
                                        key=f"btn_{unique_name}_{ext}"
                                    )
                        
                        st.info("💡 **Tip:** Clicking the red button opens the current diagram directly in the editor.")
                else:
                    st.error(" PNG not found. The Architect may have failed to generate the visual.")
            
            except Exception as e:
                st.error(f"An error occurred: {str(e)}")
    else:
        st.warning(" Please enter a prompt or upload a .tf file first.")