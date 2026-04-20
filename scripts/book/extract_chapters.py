#!/usr/bin/env python3
"""Extract chapters from the PVR Narasimha Rao textbook PDF into markdown files.

Input : docs/references/vedic_astro_textbook.pdf (gitignored)
Output: docs/book/chapters/chNN_slug.md (gitignored) + docs/book/README.md

Chapter detection is heuristic: headings look like ``24.  Kalachakra Dasa``
on a line by itself. Parts look like ``Part 2: Dasa Analysis``. We filter
out false positives where the running chapter number would go backwards
(table captions such as ``Table 41:`` happen to match the chapter pattern).
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

import fitz  # pymupdf

REPO_ROOT = Path(__file__).resolve().parents[2]
PDF_PATH = REPO_ROOT / "docs" / "references" / "vedic_astro_textbook.pdf"
OUT_ROOT = REPO_ROOT / "docs" / "book"

CHAPTER_RE = re.compile(
    r"^\s*(\d{1,2})\.\s{2,}([A-Z][A-Za-z][^\n]{2,70})\s*$", re.M
)
PART_RE = re.compile(
    r"^\s*(Part\s+\d+):\s+([A-Za-z][^\n]{2,50})\s*$", re.M
)
PAGE_HEADER_RE = re.compile(r"^\s*Part\s+\d+:\s+.*$", re.M)
PAGE_NUMBER_LINE_RE = re.compile(r"^\s*\d{1,4}\s*$", re.M)


def slugify(text: str) -> str:
    s = re.sub(r"[^A-Za-z0-9]+", "_", text.strip()).strip("_").lower()
    return s or "untitled"


def detect_chapters(doc: fitz.Document) -> list[tuple[int, int, str]]:
    """Return ``[(chapter_num, page_index_0based, title), ...]`` sorted."""
    hits: list[tuple[int, int, str]] = []
    for pn in range(doc.page_count):
        text = doc[pn].get_text()
        for m in CHAPTER_RE.finditer(text):
            hits.append((int(m.group(1)), pn, m.group(2).strip().rstrip(":").strip()))

    seen: set[int] = set()
    ordered: list[tuple[int, int, str]] = []
    last_ch = 0
    for ch, page, title in hits:
        if ch in seen:
            continue
        if ch != last_ch + 1:
            # Probably a table caption masquerading as a chapter heading.
            continue
        seen.add(ch)
        ordered.append((ch, page, title))
        last_ch = ch
    return ordered


def detect_parts(doc: fitz.Document) -> list[tuple[str, str, int]]:
    seen: set[tuple[str, str]] = set()
    parts: list[tuple[str, str, int]] = []
    for pn in range(doc.page_count):
        text = doc[pn].get_text()
        for m in PART_RE.finditer(text):
            key = (m.group(1), m.group(2).strip())
            if key in seen:
                continue
            seen.add(key)
            parts.append((m.group(1), m.group(2).strip(), pn))
    return parts


def clean_page_text(text: str) -> str:
    """Drop running headers and loose page numbers."""
    lines = text.splitlines()
    keep: list[str] = []
    for ln in lines:
        if PAGE_HEADER_RE.match(ln):
            continue
        if PAGE_NUMBER_LINE_RE.match(ln):
            continue
        keep.append(ln.rstrip())
    # Collapse runs of blank lines.
    out: list[str] = []
    blank = 0
    for ln in keep:
        if not ln.strip():
            blank += 1
            if blank <= 1:
                out.append("")
            continue
        blank = 0
        out.append(ln)
    return "\n".join(out).strip()


def extract_chapter_text(doc: fitz.Document, start: int, end: int) -> str:
    """Concatenate cleaned text for pages ``[start, end)``."""
    chunks = [clean_page_text(doc[p].get_text()) for p in range(start, end)]
    return "\n\n".join(c for c in chunks if c)


def part_for_chapter(chapter_page: int, parts: list[tuple[str, str, int]]):
    """Return the Part tuple whose page index is the greatest <= chapter_page."""
    current = None
    for p in parts:
        if p[2] <= chapter_page:
            current = p
    return current


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--pdf", type=Path, default=PDF_PATH)
    ap.add_argument("--out", type=Path, default=OUT_ROOT)
    args = ap.parse_args()

    if not args.pdf.exists():
        print(f"PDF not found: {args.pdf}", file=sys.stderr)
        return 1

    doc = fitz.open(args.pdf)
    chapters = detect_chapters(doc)
    parts = detect_parts(doc)

    if not chapters:
        print("No chapters detected.", file=sys.stderr)
        return 2

    chapters_dir = args.out / "chapters"
    chapters_dir.mkdir(parents=True, exist_ok=True)

    written: list[dict] = []
    for i, (ch, page, title) in enumerate(chapters):
        end = chapters[i + 1][1] if i + 1 < len(chapters) else doc.page_count
        body = extract_chapter_text(doc, page, end)
        part = part_for_chapter(page, parts)
        slug = slugify(title)
        filename = f"ch{ch:02d}_{slug}.md"
        md_path = chapters_dir / filename

        fm = [
            "---",
            f'chapter: {ch}',
            f'title: "{title}"',
            f'part: "{part[0] + ": " + part[1]}"' if part else 'part: ""',
            f"start_page: {page + 1}",
            f"end_page: {end}",
            "---",
            "",
            f"# Chapter {ch}. {title}",
            "",
        ]
        md_path.write_text("\n".join(fm) + body + "\n", encoding="utf-8")
        written.append({
            "chapter": ch,
            "title": title,
            "part": f"{part[0]}: {part[1]}" if part else "",
            "file": f"chapters/{filename}",
            "start_page": page + 1,
            "end_page": end,
        })
        print(f"  ch{ch:02d} {title:40s} pp.{page + 1:>4}-{end:<4} -> {filename}")

    write_index(args.out, written)
    print(f"\nWrote {len(written)} chapters to {chapters_dir}")
    print(f"Index: {args.out / 'README.md'}")
    return 0


def write_index(out_root: Path, chapters: list[dict]) -> None:
    by_part: dict[str, list[dict]] = {}
    for c in chapters:
        by_part.setdefault(c["part"] or "Front Matter", []).append(c)

    lines = [
        "# Vedic Astrology: An Integrated Approach",
        "",
        "Chapter-by-chapter markdown extraction of the PDF by P. V. R. Narasimha Rao.",
        "",
        "> These files are generated locally from `docs/references/vedic_astro_textbook.pdf`",
        "> and are **not checked into git** (see `.gitignore`).",
        "> Rebuild with `python scripts/book/extract_chapters.py`.",
        "",
    ]
    for part, items in by_part.items():
        lines.append(f"## {part}")
        lines.append("")
        for c in items:
            lines.append(
                f"- Chapter {c['chapter']}. [{c['title']}]({c['file']}) "
                f"(pp. {c['start_page']}–{c['end_page']})"
            )
        lines.append("")
    (out_root / "README.md").write_text("\n".join(lines), encoding="utf-8")


if __name__ == "__main__":
    raise SystemExit(main())
