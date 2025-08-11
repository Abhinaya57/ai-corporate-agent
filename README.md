🏢 AI Corporate Document Analyzer
This project analyzes corporate .docx documents against ADGM (Abu Dhabi Global Market) compliance rules.
It uses regex checks, RAG (Retrieval-Augmented Generation) with ADGM reference documents, and LLM-powered analysis to detect:
    Missing or incorrect jurisdiction  references
    Ambiguous contractual language
    Missing signature blocks
    Incomplete signatory requirements
    Other compliance risks based on ADGM standards
The output includes:
    An annotated .docx file with inline comments
    A JSON report with structured issue details


📂 Project Folder Structure:
ai-corporate-agent/
|-- app.py                   # Gradio web UI
|-- src/
|   |-- __init__.py
|   |-- analyzer.py          # Main analysis logic
|   |-- classifier.py        # Document type classifier
|   |-- doc_utils.py         # DOCX read & annotation utilities
|   |-- llm_utils.py         # LLM integration (OpenAI / Gemini)
|   |-- rag.py               # RAG ingestion & retrieval
|-- data_sources/            # ADGM reference documents (.pdf, .docx)
|-- docs/                    # Input documents to be analyzed
|-- outputs/                 # Annotated docs + JSON reports
|-- requirements.txt         # Python dependencies
|-- README.md                # This file
|-- .env.example             # Placeholder for environment variables


⚙️ Installation
1. Clone the repository:
    git clone <repo-url>
    cd ai-corporate-agent

2. Create and activate a virtual environment:
    python -m venv venv
    source venv/bin/activate     # Mac/Linux
    venv\Scripts\activate        # Windows

3. Install dependencies:
    pip install -r requirements.txt

4. Set environment variables (copy .env.example → .env):
    LLM_PROVIDER=openai
    OPENAI_API_KEY=your_openai_key_here
    GEMINI_API_KEY=your_gemini_key_here


📖 Usage:
1. Ingest Reference Data - Run the RAG ingestion process to index all reference materials from data_sources/:
    python src/rag.py

2. Start the Web App
    python app.py

    This will start a local Gradio interface at: http://127.0.0.1:7860


💻 Web App Workflow:
1. Upload one or more .docx files.
2. Click Analyze Document(s).
3. Review:
    Analysis Summary (issues found)
    Annotated DOCX (downloadable)
    JSON Report (downloadable)

📂 Sample Outputs:
The outputs/ folder contains:
    Annotated DOCX with highlighted issues.
    JSON reports with detailed structured analysis.
    zip folder of both annotated and JSON file


🔍 Example JSON Report:
{
  "file_analyzed": "sample_AoA.docx",
  "doc_type": "Articles of Association",
  "classification_confidence": 1.0,
  "issues_found": [
    {
      "section": "Signatures",
      "issue": "Possible missing signature block",
      "severity": "High",
      "suggestion": "Add signature block with name, position and date."
    }
  ]
}


🧠 Technology Stack
Python
Gradio - Web interface
python-docx - DOCX parsing and annotation
pypdf - PDF reference ingestion
ChromaDB - Vector store for RAG
Sentence Transformers - Embedding model
OpenAI GPT / Gemini - LLM-based analysis