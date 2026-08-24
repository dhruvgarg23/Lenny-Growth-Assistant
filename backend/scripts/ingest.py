#!/usr/bin/env python3
"""
Ingest Lenny transcripts into pgvector.
- Reads data/source/index.json + podcasts/*.md + newsletters/*.md
- Chunks 800/100 with header prepend (title + guest)
- Embeds via local MiniLM-L6-v2 (384d) batched
- Upserts documents + chunks into Postgres (HNSW)
Usage:
  python -m scripts.ingest [--reset] [--dry-run] [--limit 5]
  Inside Docker: python scripts/ingest.py
"""
import argparse
import hashlib
import json
import os
import re
import sys
from pathlib import Path
from typing import List, Dict

# Ensure backend/ is on path
BACKEND_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_DIR))

import psycopg2
import psycopg2.extras
from langchain_text_splitters import RecursiveCharacterTextSplitter

try:
    from app.config import settings
except Exception:
    # Fallback if app.config not importable (pytest)
    class _Fake:
        chunk_size = 800
        chunk_overlap = 100
        embedding_model = "sentence-transformers/all-MiniLM-L6-v2"
        vector_dim = 384
        database_url = os.getenv("DATABASE_URL", "postgresql://lenny:lenny@localhost:5432/lenny_growth")
    settings = _Fake()  # type: ignore

SOURCE_DIR = BACKEND_DIR / "data" / "source"
INDEX_PATH = SOURCE_DIR / "index.json"


def db_url_to_psycopg(url: str) -> str:
    # asyncpg URL -> psycopg2
    url = url.replace("postgresql+asyncpg://", "postgresql://")
    url = url.replace("postgresql+psycopg://", "postgresql://")
    return url

def checksum(text: str) -> str:
    return hashlib.md5(text.encode("utf-8")).hexdigest()

def load_index() -> Dict:
    with open(INDEX_PATH) as f:
        return json.load(f)

def parse_frontmatter(md_text: str) -> tuple[dict, str]:
    # Simple frontmatter: --- title: "..." ... ---  then body
    if md_text.startswith("---"):
        end = md_text.find("\n---", 3)
        if end != -1:
            fm_raw = md_text[3:end]
            body = md_text[end + 4 :].lstrip()
            fm: dict = {}
            for line in fm_raw.splitlines():
                if ":" in line:
                    k, v = line.split(":", 1)
                    fm[k.strip()] = v.strip().strip('"').strip("'")
            return fm, body
    return {}, md_text

def chunk_text(text: str, title: str, guest: str) -> List[str]:
    header = f"{title} — guest: {guest}\n\n" if guest else f"{title}\n\n"
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=getattr(settings, "chunk_size", 800),
        chunk_overlap=getattr(settings, "chunk_overlap", 100),
        separators=["\n\n", "\n", ". ", " ", ""],
    )
    # Prepend header to each chunk for retrieval context
    raw_chunks = splitter.split_text(text)
    return [header + c for c in raw_chunks]

def get_embeddings(texts: List[str]) -> List[List[float]]:
    # Use local MiniLM
    from sentence_transformers import SentenceTransformer
    model_name = getattr(settings, "embedding_model", "sentence-transformers/all-MiniLM-L6-v2")
    model = SentenceTransformer(model_name)
    # normalize for cosine
    embs = model.encode(texts, normalize_embeddings=True, batch_size=32, show_progress_bar=False)
    return embs.tolist()

def ingest(reset: bool = False, dry_run: bool = False, limit: int | None = None):
    idx = load_index()
    podcasts: List[Dict] = idx.get("podcasts", [])
    newsletters: List[Dict] = idx.get("newsletters", [])

    # newsletters in this repo: they use same keys but may lack guest
    entries: List[Dict] = []
    for p in podcasts:
        entries.append({**p, "doc_type": "podcast", "filename": p["filename"]})
    for n in newsletters:
        # newsletters may be under newsletters/*.md, some index variants name differently
        fn = n.get("filename") or n.get("path") or ""
        if not fn:
            continue
        entries.append({**n, "doc_type": "newsletter", "filename": fn})

    if limit:
        entries = entries[:limit]

    print(f"Index: {len(podcasts)} podcasts + {len(newsletters)} newsletters → ingesting {len(entries)} files")
    if dry_run:
        for e in entries[:3]:
            print(f"  - {e['filename']} — {e.get('title','')} — {e.get('word_count',0)} words")
        return

    db_url = db_url_to_psycopg(getattr(settings, "database_url", os.getenv("DATABASE_URL", "postgresql://lenny:lenny@localhost:5432/lenny_growth")))
    print(f"DB: {db_url.split('@')[-1]}")
    conn = psycopg2.connect(db_url)
    conn.autocommit = False
    cur = conn.cursor()
    cur.execute("CREATE EXTENSION IF NOT EXISTS vector")

    if reset:
        print("Reset: truncating documents, chunks...")
        cur.execute("TRUNCATE chunks, documents CASCADE")
        conn.commit()

    # Ensure tables exist — if not, warn
    cur.execute("SELECT to_regclass('public.documents'), to_regclass('public.chunks')")
    docs_reg, chunks_reg = cur.fetchone()
    if not docs_reg or not chunks_reg:
        print("ERROR: tables not found. Run alembic upgrade head first.")
        print(f"  alembic -c alembic.ini upgrade head  (DATABASE_URL={db_url})")
        sys.exit(1)

    total_chunks = 0
    total_docs = 0
    batch_texts: List[str] = []
    batch_meta: List[Dict] = []

    def flush_batch():
        nonlocal total_chunks, batch_texts, batch_meta
        if not batch_texts:
            return
        embs = get_embeddings(batch_texts)
        for meta, emb in zip(batch_meta, embs):
            # Insert chunk
            cur.execute(
                """
                INSERT INTO chunks (id, document_id, ordinal, content, embedding, token_count, model, created_at)
                VALUES (gen_random_uuid(), %s, %s, %s, %s::vector, %s, %s, NOW())
                """,
                (meta["document_id"], meta["ordinal"], meta["content"], emb, len(meta["content"].split()), getattr(settings, "embedding_model", "sentence-transformers/all-MiniLM-L6-v2")),
            )
            total_chunks += 1
        batch_texts.clear()
        batch_meta.clear()

    for entry in entries:
        rel = entry["filename"]
        fpath = SOURCE_DIR / rel
        if not fpath.exists():
            # Try alternative: podcasts/ or newsletters/
            alt = SOURCE_DIR / Path(rel).name
            if alt.exists():
                fpath = alt
            else:
                print(f"  SKIP missing: {rel} -> {fpath}")
                continue
        md_text = fpath.read_text(encoding="utf-8", errors="ignore")
        fm, body = parse_frontmatter(md_text)
        title = entry.get("title") or fm.get("title") or fpath.stem
        guest = entry.get("guest") or fm.get("guest") or ""
        word_count = entry.get("word_count") or len(md_text.split())
        cs = checksum(md_text)

        # Check existing document by source_path
        cur.execute("SELECT id, checksum FROM documents WHERE source_path = %s", (rel,))
        row = cur.fetchone()
        if row and row[1] == cs:
            print(f"  = {rel} unchanged (skip)")
            continue
        if row:
            doc_id = row[0]
            # Remove old chunks for this doc (re-embed)
            cur.execute("DELETE FROM chunks WHERE document_id = %s", (doc_id,))
            cur.execute("UPDATE documents SET title=%s, guest=%s, word_count=%s, checksum=%s WHERE id=%s", (title, guest, word_count, cs, doc_id))
            print(f"  ~ {rel} changed — reindexing")
        else:
            cur.execute(
                "INSERT INTO documents (id, source_path, title, guest, doc_type, word_count, checksum, created_at) VALUES (gen_random_uuid(), %s, %s, %s, %s, %s, %s, NOW()) RETURNING id",
                (rel, title, guest, entry.get("doc_type", "podcast"), word_count, cs),
            )
            doc_id = cur.fetchone()[0]
            print(f"  + {rel} — {title[:50]}")
            total_docs += 1

        # Chunk body (use body if parsed, else full)
        text_for_chunk = body if body else md_text
        chunks = chunk_text(text_for_chunk, title, guest)
        for i, c in enumerate(chunks):
            batch_texts.append(c)
            batch_meta.append({"document_id": doc_id, "ordinal": i, "content": c})
            if len(batch_texts) >= 32:
                flush_batch()
                conn.commit()
                print(f"    flushed {total_chunks} chunks...")

    flush_batch()
    conn.commit()
    cur.execute("SELECT COUNT(*) FROM documents")
    doc_count = cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM chunks")
    chunk_count = cur.fetchone()[0]
    print(f"\nDone. DB now: {doc_count} documents, {chunk_count} chunks. Ingested {total_docs} new docs, {total_chunks} new chunks.")

    # Refresh tsv? Trigger handles it on insert. Ensure GIN index exists
    cur.close()
    conn.close()

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--reset", action="store_true", help="Truncate existing data before ingest")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--limit", type=int, default=None, help="Only ingest first N files")
    ap.add_argument("--db-url", type=str, default=None)
    args = ap.parse_args()
    if args.db_url:
        os.environ["DATABASE_URL"] = args.db_url
        # re-read? settings already loaded, patch
        settings.database_url = args.db_url  # type: ignore
    ingest(reset=args.reset, dry_run=args.dry_run, limit=args.limit)
