#  Diagram Bot Pro

AI-powered diagram generator with iterative editing capabilities.

## Features

- ✅ Cloud Architecture Diagrams (AWS, Azure, GCP)
- ✅ Mermaid Diagrams (Flowcharts, ER, Sequence)
- ✅ D2 Modern Diagrams
- ✅ Iterative Editing (up to 10 iterations)
- ✅ Export to Draw.io, PNG, SVG
- ✅ Session Memory

## Setup

1. Clone the repository:
```bash
git clone https://github.com/yourusername/diagram-bot-pro.git
cd diagram-bot-pro
```

2. Install dependencies:
```bash
pip install -r requirements.txt
```

3. Create `.env` file:
```bash
GROQ_API_KEY=your_api_key_here
```

4. Install D2 CLI (for D2 diagrams):
```bash
# macOS
brew install d2

# Linux
curl -fsSL https://d2lang.com/install.sh | sh -s --

# Windows
# Download from https://d2lang.com
```

5. Run the app:
```bash
streamlit run app.py
```

## Usage

1. Enter a diagram description or upload a Terraform file
2. Click "Generate Diagram"
3. Make iterative edits like "remove S3 bucket" or "add Lambda function"
4. Download or edit in Draw.io/Terrastruct

## Tech Stack

- **Frontend**: Streamlit
- **AI**: AutoGen + Groq (Llama 3.3)
- **Diagram Libraries**: Diagrams, Mermaid, D2
- **Export**: Draw.io, Terrastruct

## License

MIT