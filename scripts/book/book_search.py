#!/usr/bin/env python3
"""Semantic search over the PVR textbook.

Usage:
    python scripts/book/book_search.py "what is arudha lagna"
    python scripts/book/book_search.py "vimsottari dasa" -k 8

Reads embeddings.npz built by build_embeddings.py and runs cosine similarity
against the query embedding (embeddings are L2-normalised, so a dot product
is the cosine similarity).
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_EMB = REPO_ROOT / "docs" / "book" / "embeddings.npz"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("query", nargs="+")
    ap.add_argument("--emb", type=Path, default=DEFAULT_EMB)
    ap.add_argument("-k", "--top-k", type=int, default=5)
    ap.add_argument("--chars", type=int, default=320, help="snippet length")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    if not args.emb.exists():
        print(
            f"Embeddings file not found: {args.emb}\n"
            "Run: python scripts/book/build_embeddings.py",
            file=sys.stderr,
        )
        return 1

    data = np.load(args.emb, allow_pickle=True)
    emb = data["embeddings"]
    chunks = data["chunks"]
    meta = [json.loads(s) for s in data["meta"]]
    model_name = str(data["model"][0])

    from sentence_transformers import SentenceTransformer
    model = SentenceTransformer(model_name)
    query = " ".join(args.query)
    q = model.encode(
        [query], normalize_embeddings=True, convert_to_numpy=True
    ).astype(np.float32)[0]

    scores = emb @ q
    top_idx = np.argsort(-scores)[: args.top_k]

    results = []
    for rank, idx in enumerate(top_idx, 1):
        m = meta[int(idx)]
        snippet = str(chunks[int(idx)])
        if len(snippet) > args.chars:
            snippet = snippet[: args.chars].rstrip() + "…"
        results.append({
            "rank": rank,
            "score": float(scores[int(idx)]),
            "chapter": m["chapter"],
            "title": m["title"],
            "file": m["file"],
            "pages": f"{m['start_page']}-{m['end_page']}",
            "snippet": snippet,
        })

    if args.json:
        print(json.dumps({"query": query, "results": results}, indent=2))
        return 0

    print(f"\nQuery: {query}\n")
    for r in results:
        print(
            f"[{r['rank']}] score={r['score']:.3f}  "
            f"ch{r['chapter']:02d} {r['title']}  (pp. {r['pages']})"
        )
        print(f"    {r['file']}")
        for line in r["snippet"].splitlines():
            print(f"    {line}")
        print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
