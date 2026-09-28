import re
from pathlib import Path
from typing import List, Dict, Any
from pydantic import BaseModel

class DocumentChunk(BaseModel):
    chunk_id: str
    source_file: str
    doc_title: str
    section: str
    content: str
    last_updated: str = "2026-09-01"

def parse_markdown_file(file_path: Path) -> List[DocumentChunk]:
    if not file_path.exists():
        return []
    
    text = file_path.read_text(encoding="utf-8")
    lines = text.splitlines()

    doc_title = file_path.stem.replace("_", " ").title()
    last_updated = "2026-09-01"
    
    # Extract Last Updated if present
    for line in lines[:5]:
        if "last updated" in line.lower():
            match = re.search(r"(\d{4}-\d{2}-\d{2})", line)
            if match:
                last_updated = match.group(1)

    chunks: List[DocumentChunk] = []
    current_section = "Overview"
    current_lines: List[str] = []
    chunk_idx = 0

    for line in lines:
        if line.startswith("# ") and not current_lines:
            doc_title = line.lstrip("# ").strip()
            continue
        
        # Section header
        if line.startswith("## ") or line.startswith("### "):
            if current_lines:
                body = "\n".join(current_lines).strip()
                if body:
                    chunk_id = f"{file_path.stem}-{chunk_idx}"
                    chunks.append(DocumentChunk(
                        chunk_id=chunk_id,
                        source_file=file_path.name,
                        doc_title=doc_title,
                        section=current_section,
                        content=body,
                        last_updated=last_updated
                    ))
                    chunk_idx += 1
                current_lines = []
            current_section = line.lstrip("#").strip()
        else:
            current_lines.append(line)

    if current_lines:
        body = "\n".join(current_lines).strip()
        if body:
            chunk_id = f"{file_path.stem}-{chunk_idx}"
            chunks.append(DocumentChunk(
                chunk_id=chunk_id,
                source_file=file_path.name,
                doc_title=doc_title,
                section=current_section,
                content=body,
                last_updated=last_updated
            ))

    return chunks

def load_all_kb_documents(kb_dir: Path) -> List[DocumentChunk]:
    all_chunks: List[DocumentChunk] = []
    if not kb_dir.exists():
        return all_chunks
    
    for md_file in sorted(kb_dir.glob("*.md")):
        chunks = parse_markdown_file(md_file)
        all_chunks.extend(chunks)
    
    return all_chunks
