#!/usr/bin/env python3
"""Extract chapters from the PVR Narasimha Rao textbook PDF into markdown.

Input : docs/references/vedic_astro_textbook.pdf (gitignored)
Output: docs/book/chapters/chNN_slug.md + docs/book/chapters/images/*.png
        docs/book/README.md (index)

Structural elements are preserved:
- Tables       -> markdown pipe tables (via ``page.find_tables``).
- Chart images -> extracted as PNG and linked into the markdown.
- Prose        -> text blocks sorted by reading order, with running
                  headers / loose page numbers stripped.

Chapter detection is heuristic: headings look like ``24.  Kalachakra Dasa``
on a line by itself. Parts look like ``Part 2: Dasa Analysis``. Table
captions such as ``Table 41:`` happen to match the chapter pattern, so
we filter with monotonic numbering (must be ``last_ch + 1``).
"""
from __future__ import annotations

import argparse
import re
import sys
from dataclasses import dataclass
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
PAGE_HEADER_RE = re.compile(r"^\s*Part\s+\d+:\s+.*$")
BOOK_TITLE_RE = re.compile(r"^\s*Vedic Astrology:\s+An Integrated Approach\s*$")
PAGE_NUMBER_LINE_RE = re.compile(r"^\s*\d{1,4}\s*$")


@dataclass
class Element:
    y: float
    x: float
    kind: str           # "text" | "table" | "image"
    content: str        # markdown-ready


def slugify(text: str) -> str:
    s = re.sub(r"[^A-Za-z0-9]+", "_", text.strip()).strip("_").lower()
    return s or "untitled"


def detect_chapters(doc: fitz.Document) -> list[tuple[int, int, str]]:
    hits: list[tuple[int, int, str]] = []
    for pn in range(doc.page_count):
        text = doc[pn].get_text()
        for m in CHAPTER_RE.finditer(text):
            hits.append(
                (int(m.group(1)), pn, m.group(2).strip().rstrip(":").strip())
            )
    seen: set[int] = set()
    ordered: list[tuple[int, int, str]] = []
    last_ch = 0
    for ch, page, title in hits:
        if ch in seen:
            continue
        if ch != last_ch + 1:
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


def part_for_chapter(page: int, parts: list[tuple[str, str, int]]):
    current = None
    for p in parts:
        if p[2] <= page:
            current = p
    return current


def bbox_overlap(a, b) -> bool:
    ax0, ay0, ax1, ay1 = a
    bx0, by0, bx1, by1 = b
    return not (ax1 <= bx0 or bx1 <= ax0 or ay1 <= by0 or by1 <= ay0)


def clean_line(line: str) -> str:
    s = line.strip()
    if not s:
        return ""
    if PAGE_HEADER_RE.match(s):
        return ""
    if BOOK_TITLE_RE.match(s):
        return ""
    if PAGE_NUMBER_LINE_RE.match(s):
        return ""
    return line.rstrip()


def clean_block_text(text: str) -> str:
    lines = [clean_line(ln) for ln in text.splitlines()]
    out: list[str] = []
    blank = 0
    for ln in lines:
        if not ln.strip():
            blank += 1
            if blank <= 1:
                out.append("")
            continue
        blank = 0
        out.append(ln)
    return "\n".join(out).strip()


def _md_escape_cell(value) -> str:
    if value is None:
        return " "
    s = str(value).strip()
    if not s:
        return " "
    s = s.replace("|", "\\|").replace("\r", "")
    s = re.sub(r"\s*\n\s*", " <br> ", s)
    return re.sub(r"\s+", " ", s)


def table_to_markdown(rows: list[list]) -> str:
    if not rows:
        return ""
    width = max(len(r) for r in rows)
    norm = [[_md_escape_cell(c) for c in (r + [""] * (width - len(r)))] for r in rows]
    # First row is header if it has any non-empty cell
    header = norm[0] if any(c.strip() for c in norm[0]) else [f"col{i+1}" for i in range(width)]
    body = norm[1:] if any(c.strip() for c in norm[0]) else norm
    lines = ["| " + " | ".join(header) + " |",
             "|" + "|".join(["---"] * width) + "|"]
    for r in body:
        lines.append("| " + " | ".join(r) + " |")
    return "\n".join(lines)


def extract_page_elements(
    doc: fitz.Document,
    pno: int,
    images_dir: Path,
    image_prefix: str,
    min_image_area: float = 6000.0,
) -> tuple[list[Element], int]:
    """Return ordered elements for one page + number of images saved."""
    page = doc[pno]
    elements: list[Element] = []

    # --- Tables ---
    table_bboxes: list[tuple[float, float, float, float]] = []
    try:
        tabs = page.find_tables().tables
    except Exception:
        tabs = []
    for t in tabs:
        try:
            rows = t.extract()
        except Exception:
            continue
        md = table_to_markdown(rows)
        if not md:
            continue
        x0, y0, x1, y1 = t.bbox
        table_bboxes.append((x0, y0, x1, y1))
        elements.append(Element(y=y0, x=x0, kind="table", content=md))

    # --- Images ---
    image_count = 0
    try:
        infos = page.get_image_info(xrefs=True)
    except Exception:
        infos = []
    for idx, info in enumerate(infos):
        bbox = info.get("bbox")
        xref = info.get("xref")
        if not bbox or not xref:
            continue
        x0, y0, x1, y1 = bbox
        if (x1 - x0) * (y1 - y0) < min_image_area:
            continue
        try:
            img = doc.extract_image(xref)
        except Exception:
            continue
        ext = img.get("ext", "png")
        fname = f"{image_prefix}_p{pno + 1:04d}_{idx + 1}.{ext}"
        (images_dir / fname).write_bytes(img["image"])
        image_count += 1
        md = f"![page {pno + 1}](images/{fname})"
        elements.append(Element(y=y0, x=x0, kind="image", content=md))

    # --- Text blocks (skip anything that sits inside a table bbox) ---
    text_blocks = page.get_text("blocks")
    for b in text_blocks:
        x0, y0, x1, y1, text, *_ = b
        if not text or not text.strip():
            continue
        if any(bbox_overlap((x0, y0, x1, y1), tb) for tb in table_bboxes):
            continue
        cleaned = clean_block_text(text)
        if not cleaned:
            continue
        elements.append(Element(y=y0, x=x0, kind="text", content=cleaned))

    elements.sort(key=lambda e: (round(e.y, 1), round(e.x, 1)))
    return elements, image_count


def render_chapter(
    doc: fitz.Document,
    start: int,
    end: int,
    images_dir: Path,
    image_prefix: str,
) -> tuple[str, int]:
    parts: list[str] = []
    last_kind: str | None = None
    total_imgs = 0
    for pno in range(start, end):
        elements, n_imgs = extract_page_elements(doc, pno, images_dir, image_prefix)
        total_imgs += n_imgs
        for el in elements:
            if last_kind == "table" or el.kind == "table":
                sep = "\n\n"
            elif last_kind == "image" or el.kind == "image":
                sep = "\n\n"
            elif last_kind is None:
                sep = ""
            else:
                sep = "\n\n"
            parts.append(sep + el.content)
            last_kind = el.kind
    body = "".join(parts).strip()
    # Collapse excessive blank lines (never more than one empty line in a row).
    body = re.sub(r"\n{3,}", "\n\n", body)
    return body, total_imgs


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
    images_dir = chapters_dir / "images"
    chapters_dir.mkdir(parents=True, exist_ok=True)
    images_dir.mkdir(parents=True, exist_ok=True)
    # Purge old images to avoid accumulating stale files between runs.
    for old in images_dir.glob("*"):
        if old.is_file():
            old.unlink()

    written: list[dict] = []
    for i, (ch, page, title) in enumerate(chapters):
        end = chapters[i + 1][1] if i + 1 < len(chapters) else doc.page_count
        slug = slugify(title)
        image_prefix = f"ch{ch:02d}"
        body, n_imgs = render_chapter(doc, page, end, images_dir, image_prefix)
        part = part_for_chapter(page, parts)
        filename = f"ch{ch:02d}_{slug}.md"
        md_path = chapters_dir / filename

        fm = [
            "---",
            f"chapter: {ch}",
            f'title: "{title}"',
            f'part: "{part[0] + ": " + part[1]}"' if part else 'part: ""',
            f"start_page: {page + 1}",
            f"end_page: {end}",
            f"images: {n_imgs}",
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
            "images": n_imgs,
        })
        print(
            f"  ch{ch:02d} {title:40s} pp.{page + 1:>4}-{end:<4} "
            f"imgs={n_imgs:>3} -> {filename}"
        )

    write_index(args.out, written)
    print(f"\nWrote {len(written)} chapters to {chapters_dir}")
    print(f"Images: {images_dir}")
    print(f"Index : {args.out / 'README.md'}")
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
            img_note = f" · {c['images']} image(s)" if c.get("images") else ""
            lines.append(
                f"- Chapter {c['chapter']}. [{c['title']}]({c['file']}) "
                f"(pp. {c['start_page']}–{c['end_page']}){img_note}"
            )
        lines.append("")
    (out_root / "README.md").write_text("\n".join(lines), encoding="utf-8")


if __name__ == "__main__":
    raise SystemExit(main())
