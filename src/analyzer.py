import os
import re
import json
import logging
from datetime import datetime, timezone

from src.classifier import classify_doc_type
from src.doc_utils import annotate_docx, read_docx_paragraphs
from src.rag import retrieve_relevant_sections
from src.llm_utils import analyze_with_llm  # newer robust LLM utils

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# --- Config / Paths ---
ROOT = os.path.dirname(__file__)  # src/
PROJECT_ROOT = os.path.join(ROOT, "..")
DOCS_DIR = os.path.join(PROJECT_ROOT, "docs")
OUTPUTS_DIR = os.path.join(PROJECT_ROOT, "outputs")
CHROMA_DIR = os.path.join(PROJECT_ROOT, "chroma_db")
COLLECTION_NAME = "adgm_refs"

# Ensure outputs dir exists
os.makedirs(OUTPUTS_DIR, exist_ok=True)

# --- Regex patterns ---
JURIS_REGEX = re.compile(r'\b(abu dhabi global market|adgm|abu dhabi|united arab emirates|uae|dubai)\b', re.IGNORECASE)
NON_ADGM_JURIS_REGEX = re.compile(r'\b(united kingdom|uk|england|usa|united states|federal court|dubai international financial centre|difc)\b', re.IGNORECASE)
AMBIGUOUS_REGEX = re.compile(r'\b(may\b|best endeavou?r?s\b|best efforts|endeavour to|could\b)\b', re.IGNORECASE)
SIGNATURE_REGEX = re.compile(r'(signed[:\s]|signature[:\s]|sig[:\s])', re.IGNORECASE)
SINGLE_SIGNATORY_REGEX = re.compile(r'\b(one|1)\b.*(authorized signator|authorized signatory|signatory)\b', re.IGNORECASE)

def _sanitize_name(name_noext: str) -> str:
    """Sanitize file base name for safe filesystem use."""
    safe = re.sub(r'[^A-Za-z0-9_.-]', '_', name_noext)[:120]
    return safe

def analyze_file(docx_path, save_annotated=True, use_llm=True):
    """
    Analyze a .docx file for ADGM compliance issues.
    Returns a report dict with metadata and file paths.
    """
    basename = os.path.basename(docx_path)
    name_noext = os.path.splitext(basename)[0]
    safe_name = _sanitize_name(name_noext)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")

    # 1) classify doc type
    doc_type, confidence = classify_doc_type(docx_path)

    # 2) read paragraphs
    paras = read_docx_paragraphs(docx_path)

    # 3) prepare results containers
    issues = []
    annotations = []

    # 4) Retrieve RAG evidence helper (normalized)
    def retrieve_evidence(query_text, n_results=2):
        try:
            docs = retrieve_relevant_sections(query_text, n_results=n_results)
            evidence = []
            for item in docs:
                if isinstance(item, dict):
                    evidence.append({
                        "text": item.get("text", ""),
                        "meta": item.get("meta", {}),
                        "score": item.get("score", None)
                    })
                else:
                    evidence.append({"text": str(item), "meta": {}, "score": None})
            return evidence
        except Exception:
            logger.exception("RAG retrieval failed")
            return []

    # 5) Document-level checks
    whole_text = "\n".join([p for _, p in paras])

    # Missing signature check
    if not SIGNATURE_REGEX.search(whole_text.lower()):
        issue = {
            "document": basename,
            "doc_type": doc_type,
            "section": "Signatures",
            "issue": "Possible missing signature block",
            "severity": "High",
            "suggestion": "Add signature block with name, position and date.",
            "evidence": retrieve_evidence("signature block example", n_results=2)
        }
        issues.append(issue)
        annotations.append((len(paras)-1 if paras else 0, issue["suggestion"]))

    # 6) Paragraph-level checks
    for idx, text in paras:
        lower = text.lower()

        # Skip empty paragraphs
        if not lower.strip():
            continue

        # Check for non-ADGM jurisdiction mentions
        m_non = NON_ADGM_JURIS_REGEX.search(lower)
        if m_non:
            found = m_non.group(0)
            issue = {
                "document": basename,
                "doc_type": doc_type,
                "section": f"Paragraph {idx}",
                "issue": f"Non-ADGM jurisdiction referenced: '{found}'",
                "severity": "High",
                "suggestion": "Change jurisdiction to ADGM/ADGM Courts if incorporation is in ADGM.",
                "evidence": retrieve_evidence("ADGM jurisdiction requirement", n_results=2)
            }
            issues.append(issue)
            annotations.append((idx, f"Jurisdiction appears non-ADGM: {found}. Suggest: use ADGM jurisdiction."))

        # Ambiguous language detection
        if AMBIGUOUS_REGEX.search(lower):
            issue = {
                "document": basename,
                "doc_type": doc_type,
                "section": f"Paragraph {idx}",
                "issue": "Potentially ambiguous/non-binding language (may, best endeavours, etc.)",
                "severity": "Medium",
                "suggestion": "Consider using stronger binding language (e.g., 'shall') for obligations.",
                "evidence": retrieve_evidence("binding language shall vs may", n_results=1)
            }
            issues.append(issue)
            annotations.append((idx, "Potentially ambiguous language found. Replace with stronger terms."))

        # Single authorized signatory check
        if SINGLE_SIGNATORY_REGEX.search(lower):
            issue = {
                "document": basename,
                "doc_type": doc_type,
                "section": f"Paragraph {idx}",
                "issue": "Only one authorized signatory specified",
                "severity": "Medium",
                "suggestion": "Confirm checklist requirement; consider adding an additional authorized signatory.",
                "evidence": retrieve_evidence("signature requirement multiple signatories", n_results=1)
            }
            issues.append(issue)
            annotations.append((idx, "Only one authorized signatory specified. Consider adding another."))

    # 7) LLM Analysis (optional)
    if use_llm:
        try:
            # Limit document excerpt length for LLM prompt
            doc_excerpt = whole_text if len(whole_text) < 20000 else whole_text[:20000]
            llm_issues = analyze_with_llm(doc_excerpt, doc_type)
            if isinstance(llm_issues, list):
                for li in llm_issues:
                    if not isinstance(li, dict) or "issue" not in li:
                        continue
                    li_norm = {
                        "document": basename,
                        "doc_type": doc_type,
                        "section": li.get("section", "LLM Analysis"),
                        "issue": li.get("issue"),
                        "severity": li.get("severity", "Low"),
                        "suggestion": li.get("suggestion", ""),
                        "evidence": []  # LLM issues currently have no RAG evidence
                    }
                    issues.append(li_norm)
        except Exception:
            logger.exception("LLM_ANALYSIS failed")

    # 8) Build summary JSON
    report = {
        "file_analyzed": basename,
        "doc_type": doc_type,
        "classification_confidence": confidence,
        "num_paragraphs": len(paras),
        "issues_found": issues,
        "annotated_file": None,
        "report_file": None,
        "analyzed_at": timestamp
    }

    # 9) Annotate DOCX output with issues
    annotated_path = os.path.abspath(os.path.join(OUTPUTS_DIR, f"annotated_{safe_name}.docx"))
    if save_annotated and annotations:
        try:
            annotate_docx(docx_path, annotations, annotated_path)
            report["annotated_file"] = annotated_path
        except Exception:
            logger.exception("Failed to annotate docx")
            report["annotated_file"] = None
    else:
        # If no annotations, still save a copy of original doc to outputs for traceability
        try:
            from docx import Document as _Doc
            doc = _Doc(docx_path)
            doc.save(annotated_path)
            report["annotated_file"] = annotated_path
        except Exception:
            report["annotated_file"] = None

    # 10) Save JSON report robustly
    report_path = os.path.abspath(os.path.join(OUTPUTS_DIR, f"report_{safe_name}_{timestamp}.json"))
    try:
        with open(report_path, "w", encoding="utf-8") as f:
            json.dump(report, f, indent=2, ensure_ascii=False)
        report["report_file"] = report_path
    except Exception:
        logger.exception("Failed to save report JSON")
        report["report_file"] = None

    return report


if __name__ == "__main__":
    for filename in os.listdir(DOCS_DIR):
        # Skip temporary files like ~$ which cause errors
        if filename.startswith("~$") or filename.startswith("."):
            logger.info(f"[Analyzer] Skipping temporary or hidden file: {filename}")
            continue

        file_path = os.path.join(DOCS_DIR, filename)
        if os.path.isfile(file_path) and filename.lower().endswith(".docx"):
            logger.info(f"Analyzing: {filename}")
            try:
                report = analyze_file(file_path)
                logger.info(f"Found {len(report['issues_found'])} issues in {filename}")
            except Exception as e:
                logger.error(f"[Analyzer] Error analyzing {filename}: {e}")
