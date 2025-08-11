import os
import shutil
import zipfile
import gradio as gr
from datetime import datetime

from src.analyzer import analyze_file

# Paths
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DOCS_DIR = os.path.join(BASE_DIR, "docs")
OUTPUTS_DIR = os.path.join(BASE_DIR, "outputs")
os.makedirs(DOCS_DIR, exist_ok=True)
os.makedirs(OUTPUTS_DIR, exist_ok=True)

def process_uploads(uploaded_files):
    """
    Handle uploaded files, save them to docs/, run analysis, return results.
    Returns a summary string and a path to a zip containing outputs (annotated + JSON).
    """
    if not uploaded_files:
        return "No file uploaded.", None

    # Ensure list
    if not isinstance(uploaded_files, list):
        uploaded_files = [uploaded_files]

    summaries = []
    produced_files = []

    for uf in uploaded_files:
        uf_path = str(uf)
        filename = os.path.basename(uf_path)
        save_path = os.path.join(DOCS_DIR, filename)

        try:
            shutil.copy(uf_path, save_path)
        except Exception as e:
            summaries.append(f"{filename}: ❌ Error saving file ({e})")
            continue

        try:
            report = analyze_file(save_path, save_annotated=True)
            issue_count = len(report.get("issues_found", []))
            doc_type = report.get("doc_type", "Unknown")
            conf = report.get("classification_confidence", 0.0)
            summaries.append(f"**{filename}** — {doc_type} (conf: {conf:.2f}) — {issue_count} issue(s) found.")
            if report.get("annotated_file"):
                produced_files.append(report["annotated_file"])
            if report.get("report_file"):
                produced_files.append(report["report_file"])
        except Exception as e:
            summaries.append(f"{filename}: ❌ Error during analysis ({e})")

    # Create zip of produced files for download
    if produced_files:
        zip_name = f"analysis_outputs_{datetime.utcnow().strftime('%Y%m%dT%H%M%SZ')}.zip"
        zip_path = os.path.join(OUTPUTS_DIR, zip_name)
        with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
            for p in produced_files:
                if p and os.path.exists(p):
                    try:
                        zf.write(p, arcname=os.path.basename(p))
                    except Exception:
                        pass
        return "\n\n".join(summaries), zip_path
    else:
        return "\n\n".join(summaries), None

# Build Gradio UI
with gr.Blocks(title="🏢 AI Corporate Document Analyzer") as demo:
    gr.Markdown("# 🏢 AI Corporate Document Analyzer")
    gr.Markdown(
        "Upload one or more `.docx` files to analyze them against ADGM compliance rules."
    )

    file_input = gr.File(
        file_types=[".docx"],
        type="filepath",
        file_count="multiple",
        label="Upload DOCX File(s)"
    )

    analyze_btn = gr.Button("Analyze Document(s)")

    output_text = gr.Markdown(label="Analysis Summary")
    output_zip = gr.File(label="Download All Outputs (ZIP)")

    analyze_btn.click(
        fn=process_uploads,
        inputs=file_input,
        outputs=[output_text, output_zip]
    )

if __name__ == "__main__":
    demo.launch()
