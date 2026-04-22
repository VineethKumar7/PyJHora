#!/usr/bin/env python3
"""Chunk the extracted chapter markdowns and build a local vector store.

Reads   : docs/book/chapters/*.md
Writes  : docs/book/embeddings.npz  (chunks, metadata, float32 embeddings)

Embedding model: sentence-transformers/all-MiniLM-L6-v2 (384-d, ~90 MB, CPU-ok).
Default chunk unit is one markdown **paragraph** — blocks separated by blank
lines. Tables and image links stay as their own paragraphs so search can land
on a specific table or diagram. ``--words`` switches back to sliding word
windows if you want coarser retrieval.
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


IMAGE_ONLY_RE = re.compile(r"^!\[[^\]]*\]\([^\)]+\)\s*$")


def chunk_text(text: str, words_per_chunk: int, overlap: int) -> list[tuple[int, int, str]]:
    """Yield ``(word_start, word_end, chunk_text)`` using sliding word windows."""
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


def chunk_paragraphs(
    text: str,
    min_chars: int,
    merge_under: int,
) -> list[tuple[str, str]]:
    """Yield ``(kind, paragraph_text)`` where kind is 'text' | 'table' | 'image'.

    A paragraph is a block separated by blank lines. Very short paragraphs
    (e.g. stray section-number lines) are merged forward into the next one so
    we do not litter the index with near-empty chunks.
    """
    raw_paras = re.split(r"\n\s*\n+", text)
    cleaned: list[tuple[str, str]] = []
    buffer = ""
    for raw in raw_paras:
        para = raw.strip()
        if not para:
            continue
        if IMAGE_ONLY_RE.match(para):
            if buffer:
                cleaned.append(("text", buffer.strip()))
                buffer = ""
            cleaned.append(("image", para))
            continue
        if para.lstrip().startswith("|") and "|" in para:
            if buffer:
                cleaned.append(("text", buffer.strip()))
                buffer = ""
            cleaned.append(("table", para))
            continue
        candidate = (buffer + "\n\n" + para).strip() if buffer else para
        if len(candidate) < merge_under:
            buffer = candidate
            continue
        cleaned.append(("text", candidate))
        buffer = ""
    if buffer:
        cleaned.append(("text", buffer.strip()))

    # Drop noise that is still below the minimum size.
    return [(k, p) for k, p in cleaned if len(p) >= min_chars or k in {"table", "image"}]


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
    ap.add_argument(
        "--mode", choices=["paragraph", "window"], default="paragraph",
        help="paragraph: one chunk per MD paragraph; window: sliding words",
    )
    ap.add_argument("--words", type=int, default=350, help="window mode: words per chunk")
    ap.add_argument("--overlap", type=int, default=60, help="window mode: word overlap")
    ap.add_argument("--min-chars", type=int, default=40, help="paragraph mode: drop shorter text paragraphs")
    ap.add_argument("--merge-under", type=int, default=80, help="paragraph mode: merge a short paragraph into the next")
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
        base = {
            "chapter": int(fm.get("chapter", 0) or 0),
            "title": fm.get("title", first_heading(body)),
            "part": fm.get("part", ""),
            "file": f"chapters/{path.name}",
            "start_page": int(fm.get("start_page", 0) or 0),
            "end_page": int(fm.get("end_page", 0) or 0),
        }
        if args.mode == "paragraph":
            for i, (kind, para) in enumerate(
                chunk_paragraphs(body, args.min_chars, args.merge_under)
            ):
                chunks.append(para)
                meta.append({**base, "chunk_index": i, "kind": kind})
        else:
            for i, (ws, we, chunk) in enumerate(
                chunk_text(body, args.words, args.overlap)
            ):
                chunks.append(chunk)
                meta.append({
                    **base,
                    "chunk_index": i,
                    "kind": "text",
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
