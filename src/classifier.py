import os
import docx2txt
from src.llm_utils import get_llm_response

# Keyword dictionary for document classification
DOC_TYPE_KEYWORDS = {
    "Articles of Association": [
        "articles of association",
        "aoa",
        "company articles"
    ],
    "Memorandum of Association": [
        "memorandum of association",
        "moa",
        "memorandum"
    ],
    "UBO Declaration Form": [
        "ultimate beneficial owner",
        "ubo declaration",
        "ubo form"
    ],
    "Register of Members and Directors": [
        "register of members",
        "register of directors"
    ],
    "Board Resolution": [
        "board resolution",
        "resolution of the board",
        "written resolution"
    ],
    "Employment Contract": [
        "employment contract",
        "employee agreement",
        "terms of employment"
    ]
}

def classify_doc_type(docx_path, use_fallback=True):
    """
    Classify the type of a .docx based on keyword matches.
    If no keyword match found and use_fallback=True, calls LLM for classification.
    Returns a tuple: (doc_type, confidence_score)
    """
    try:
        text = docx2txt.process(docx_path) or ""
    except Exception as e:
        print(f"[Classifier] Error reading {docx_path}: {e}")
        return "Unknown", 0.0

    if not text.strip():
        # Empty document
        return "Unknown", 0.0

    text_lower = text.lower()
    scores = {}

    # Simple keyword matching count per doc type
    for doc_type, keywords in DOC_TYPE_KEYWORDS.items():
        for kw in keywords:
            if kw in text_lower:
                scores[doc_type] = scores.get(doc_type, 0) + 1

    if scores:
        # Choose best matching doc type by highest keyword count normalized by total keywords
        best_match, best_count = max(scores.items(), key=lambda x: x[1])
        total_keywords = max(1, len(DOC_TYPE_KEYWORDS.get(best_match, [])))
        confidence = best_count / total_keywords
        confidence = min(1.0, confidence)
        print(f"[Classifier] Keyword match: {best_match} (conf={confidence:.2f})")
        return best_match, round(confidence, 2)

    # Fallback: use LLM if no keyword matches
    if use_fallback:
        try:
            snippet = text[:4000]  # limit input size for LLM
            llm_prompt = (
                "You are an ADGM compliance assistant. "
                "Classify the following document into one of these categories:\n"
                f"{', '.join(DOC_TYPE_KEYWORDS.keys())}.\n"
                "Return ONLY the single category name (exactly), or 'Unknown'.\n\n"
                f"Document content:\n{snippet}"
            )
            llm_response = get_llm_response(llm_prompt, temperature=0)
            doc_type = None
            if llm_response:
                for candidate in DOC_TYPE_KEYWORDS.keys():
                    if candidate.lower() in llm_response.lower():
                        doc_type = candidate
                        break

            if not doc_type:
                doc_type = "Unknown"

            confidence = 0.8 if doc_type != "Unknown" else 0.35
            print(f"[Classifier] LLM fallback classification: {doc_type} (conf={confidence:.2f})")
            return doc_type, confidence

        except Exception as e:
            print(f"[Classifier] LLM fallback failed: {e}")

    return "Unknown", 0.0


if __name__ == "__main__":
    test_path = os.path.join(os.path.dirname(__file__), "..", "docs", "sample_AoA.docx")
    if os.path.exists(test_path):
        doc_type, conf = classify_doc_type(test_path)
        print(f"Detected type: {doc_type} (confidence: {conf})")
    else:
        print("[Classifier] No sample file found for testing.")
