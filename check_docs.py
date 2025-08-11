import os
from docx import Document

docs_dir = "docs"

for fname in os.listdir(docs_dir):
    if fname.endswith(".docx") and not fname.startswith("~$"):
        path = os.path.join(docs_dir, fname)
        try:
            Document(path)
            print(f"[OK] {fname}")
        except Exception as e:
            print(f"[ERROR] {fname}: {e}")
