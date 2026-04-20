#!/usr/bin/env python3
"""Chunk the extracted chapter markdowns and build a local vector store.

Reads   : docs/book/chapters/*.md
Writes  : docs/book/embeddings.npz  (chunks, metadata, float32 embeddings)

Embedding model: sentence-transformers/all-MiniLM-L6-v2 (384-d, ~90 MB, CPU-ok).
Chunk size defaults to ~350 words with 60-word overlap — tuned so each chunk
lands around 500 tokens (the sweet spot for retrieval quality with this model).
"""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

import numpy as np

REPO_ROOT = Path(__file__).resolve().parents[2]
BOOK_ROOT = REPO_ROOT / "docs" / "book"
CHAPTERS_DIR = BOOK_ROOT / "chapters"
OUT_PATH = BOOK_ROOT / "embeddings.npz"

FRONTMATTER_RE = re.compile(r"^---\n(.*?)\n---\n", re.S)


def parse_frontmatter(text: str) -> tuple[dict, str]:
    m = FRONTMATTER_RE.match(text)
    if not m:
        return {}, text
    meta: dict = {}
    for line in m.group(1).splitlines():
        if ":" not in line:
            continue
        k, v = line.split(":", 1)
        meta[k.strip()] = v.strip().strip('"')
    return meta, text[m.end():]


def chunk_text(text: str, words_per_chunk: int, overlap: int) -> list[tuple[int, int, str]]:
    """Yield ``(word_start, word_end, chunk_text)``."""
    words = text.split()
    if not words:
        return []
    step = max(1, words_per_chunk - overlap)
    out: list[tuple[int, int, str]] = []
    i = 0
    while i < len(words):
        end = min(len(words), i + words_per_chunk)
        out.append((i, end, " ".join(words[i:end])))
        if end == len(words):
            break
        i += step
    return out


def first_heading(text: str) -> str:
    for line in text.splitlines():
        s = line.strip()
        if s.startswith("#"):
            return s.lstrip("#").strip()
    return ""


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--chapters", type=Path, default=CHAPTERS_DIR)
    ap.add_argument("--out", type=Path, default=OUT_PATH)
    ap.add_argument("--model", default="sentence-transformers/all-MiniLM-L6-v2")
    ap.add_argument("--words", type=int, default=350, help="words per chunk")
    ap.add_argument("--overlap", type=int, default=60, help="word overlap")
    ap.add_argument("--batch", type=int, default=64)
    args = ap.parse_args()

    if not args.chapters.is_dir():
        raise SystemExit(
            f"{args.chapters} does not exist — run extract_chapters.py first."
        )

    files = sorted(args.chapters.glob("ch*.md"))
    if not files:
        raise SystemExit(f"No chapter files under {args.chapters}.")

    print(f"Loading model {args.model}…")
    from sentence_transformers import SentenceTransformer
    model = SentenceTransformer(args.model)

    chunks: list[str] = []
    meta: list[dict] = []
    for path in files:
        raw = path.read_text(encoding="utf-8")
        fm, body = parse_frontmatter(raw)
        # Drop the top H1 so the body we embed is the actual prose.
        body = re.sub(r"^#[^\n]*\n", "", body, count=1).strip()
        for i, (ws, we, chunk) in enumerate(
            chunk_text(body, args.words, args.overlap)
        ):
            chunks.append(chunk)
            meta.append({
                "chapter": int(fm.get("chapter", 0) or 0),
                "title": fm.get("title", first_heading(body)),
                "part": fm.get("part", ""),
                "file": f"chapters/{path.name}",
                "start_page": int(fm.get("start_page", 0) or 0),
                "end_page": int(fm.get("end_page", 0) or 0),
                "chunk_index": i,
                "word_start": ws,
                "word_end": we,
            })

    print(f"Embedding {len(chunks)} chunks…")
    emb = model.encode(
        chunks,
        batch_size=args.batch,
        show_progress_bar=True,
        normalize_embeddings=True,
        convert_to_numpy=True,
    ).astype(np.float32)

    args.out.parent.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(
        args.out,
        embeddings=emb,
        chunks=np.array(chunks, dtype=object),
        meta=np.array([json.dumps(m) for m in meta], dtype=object),
        model=np.array([args.model], dtype=object),
    )
    print(f"Wrote {args.out} — {emb.shape[0]} chunks × {emb.shape[1]} dims")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
