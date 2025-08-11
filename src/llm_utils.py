# src/llm_utils.py
import os
import re
import json
import time

# Determine LLM provider via environment variable
PROVIDER = os.getenv("LLM_PROVIDER", "openai").lower()  # "openai" or "gemini"

# Lazy imports to avoid raising at import-time if keys missing
_openai_client = None
_genai = None

def _init_openai():
    global _openai_client
    if _openai_client is not None:
        return _openai_client
    try:
        from openai import OpenAI
    except Exception as e:
        raise RuntimeError("OpenAI SDK not installed") from e
    OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
    if not OPENAI_API_KEY:
        raise ValueError("Missing OPENAI_API_KEY environment variable")
    _openai_client = OpenAI(api_key=OPENAI_API_KEY)
    return _openai_client

def _init_gemini():
    global _genai
    try:
        import google.generativeai as genai
    except Exception as e:
        raise RuntimeError("google.generativeai not installed") from e
    GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
    if not GEMINI_API_KEY:
        raise ValueError("Missing GEMINI_API_KEY environment variable")
    genai.configure(api_key=GEMINI_API_KEY)
    _genai = genai
    return _genai

def get_llm_response(prompt: str, temperature: float = 0.0, timeout: int = 30) -> str:
    """
    Generic prompt completion function. Returns raw text response.
    """
    try:
        if PROVIDER == "openai":
            client = _init_openai()
            response = client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[{"role": "user", "content": prompt}],
                temperature=temperature,
            )
            return response.choices[0].message.content
        elif PROVIDER == "gemini":
            genai = _init_gemini()
            model = genai.GenerativeModel("gemini-1.5-flash")
            response = model.generate_content(prompt, temperature=temperature)
            return response.text
        else:
            raise ValueError(f"Unsupported LLM_PROVIDER: {PROVIDER}")
    except Exception as e:
        print(f"[LLM_UTILS] Error in get_llm_response: {e}")
        return ""

def _safe_extract_json(text: str):
    """
    Try to extract a JSON object/array from free text.
    Returns parsed JSON or raises ValueError.
    """
    # Try direct load first
    try:
        return json.loads(text)
    except Exception:
        pass
    # Attempt to find a large JSON snippet
    match = re.search(r'(\[.*\])', text, flags=re.DOTALL)
    if not match:
        match = re.search(r'(\{.*\})', text, flags=re.DOTALL)
    if not match:
        raise ValueError("No JSON found in LLM response")
    candidate = match.group(1)
    return json.loads(candidate)

def analyze_with_llm(doc_text: str, doc_type: str, max_retries: int = 2) -> list[dict]:
    """
    Sends document text and type to the LLM for compliance issue detection.
    Returns a list of issues in JSON format:
    [{ "issue": str, "severity": str, "suggestion": str }, ...]
    """
    prompt = f"""
You are an expert in ADGM corporate compliance.
Given the following document type: {doc_type}
Analyze the text below for possible compliance issues, ambiguities, or missing required clauses.

Document Text:
\"\"\"{doc_text}\"\"\"

Return the issues as a JSON array, each issue containing:
- issue (string)
- severity (High/Medium/Low)
- suggestion (string)

Important:
Return ONLY a JSON array. Do not include any explanatory text or headers.
    """

    for attempt in range(max_retries + 1):
        try:
            resp_text = get_llm_response(prompt, temperature=0)
            if not resp_text:
                return []
            parsed = _safe_extract_json(resp_text)
            # Basic validation
            if isinstance(parsed, list):
                normalized = []
                for item in parsed:
                    if not isinstance(item, dict) or "issue" not in item:
                        continue
                    normalized.append({
                        "issue": item.get("issue", ""),
                        "severity": item.get("severity", "Low"),
                        "suggestion": item.get("suggestion", "")
                    })
                return normalized
            else:
                return []
        except Exception as e:
            print(f"[LLM_UTILS] analyze_with_llm attempt {attempt} failed: {e}")
            time.sleep(1 + attempt)
            continue

    return []


if __name__ == "__main__":
    print("LLM utils loaded. Provider:", PROVIDER)
