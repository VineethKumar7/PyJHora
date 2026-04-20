# Book extraction + RAG pipeline

Three scripts that turn the PVR Narasimha Rao textbook PDF into searchable
markdown and a local vector store. The book itself is **not checked into
git** — keep your copy at `docs/references/vedic_astro_textbook.pdf`
(download from <https://www.vedicastrologer.org/articles/vedic_astro_textbook.pdf>).

## Pipeline

```bash
# 1) PDF → chapter markdown files + docs/book/README.md index
python scripts/book/extract_chapters.py

# 2) MDs → docs/book/embeddings.npz
python scripts/book/build_embeddings.py

# 3) Semantic search
python scripts/book/book_search.py "what is arudha lagna" -k 5
```

All three outputs (`docs/book/chapters/*.md`, `docs/book/README.md`,
`docs/book/embeddings.npz`) live under `docs/book/`, which is gitignored.

## Options

- `extract_chapters.py --pdf PATH --out DIR`
- `build_embeddings.py --words 350 --overlap 60 --model sentence-transformers/all-MiniLM-L6-v2`
- `book_search.py QUERY -k 10 --json`

## Notes

- The extractor detects chapters heuristically (`N.  Title` patterns) and
  drops running page headers / loose page numbers from the prose.
- Embedding model defaults to `all-MiniLM-L6-v2` (384-d, fast on CPU).
  Swap it with `--model` if you want a larger encoder.
- Embeddings are L2-normalised, so similarity is a single dot product;
  no FAISS / ChromaDB dependency.
