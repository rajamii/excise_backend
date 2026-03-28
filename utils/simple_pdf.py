from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable


def _escape_pdf_text(text: str) -> str:
    return (
        str(text)
        .replace("\\", "\\\\")
        .replace("(", "\\(")
        .replace(")", "\\)")
        .replace("\r\n", "\n")
        .replace("\r", "\n")
    )


def _wrap_line(text: str, max_chars: int) -> list[str]:
    text = str(text or "").strip()
    if not text:
        return [""]
    if len(text) <= max_chars:
        return [text]

    words = text.split()
    lines: list[str] = []
    current = ""
    for w in words:
        if not current:
            current = w
            continue
        if len(current) + 1 + len(w) <= max_chars:
            current = f"{current} {w}"
        else:
            lines.append(current)
            current = w
    if current:
        lines.append(current)
    return lines or [text[:max_chars]]


def paginate_lines(lines: Iterable[str], max_chars: int = 95, lines_per_page: int = 52) -> list[list[str]]:
    wrapped: list[str] = []
    for line in lines:
        for part in _wrap_line(line, max_chars=max_chars):
            wrapped.append(part)
    pages: list[list[str]] = []
    for i in range(0, len(wrapped), lines_per_page):
        pages.append(wrapped[i : i + lines_per_page])
    return pages or [[]]


@dataclass(frozen=True)
class PdfPage:
    lines: list[str]


def build_text_pdf(pages: list[PdfPage], *, font_size: int = 10) -> bytes:
    # A4 portrait points
    width = 595
    height = 842
    left = 44
    top = height - 50
    leading = int(max(12, round(font_size * 1.35)))

    def content_stream(page_lines: list[str]) -> bytes:
        parts: list[str] = []
        parts.append("BT")
        parts.append(f"/F1 {font_size} Tf")
        parts.append(f"{left} {top} Td")
        parts.append(f"{leading} TL")
        for ln in page_lines:
            esc = _escape_pdf_text(ln)
            parts.append(f"({esc}) Tj")
            parts.append("T*")
        parts.append("ET")
        return ("\n".join(parts) + "\n").encode("utf-8")

    # Object allocation
    # 1 Catalog, 2 Pages, 3 Font, page objs..., content objs...
    page_count = len(pages)
    first_page_obj = 4
    first_content_obj = first_page_obj + page_count
    font_obj = 3

    objects: list[tuple[int, bytes]] = []

    # Catalog
    objects.append((1, b"<< /Type /Catalog /Pages 2 0 R >>"))

    # Pages root
    kids = " ".join([f"{first_page_obj + i} 0 R" for i in range(page_count)])
    objects.append((2, f"<< /Type /Pages /Kids [ {kids} ] /Count {page_count} >>".encode("utf-8")))

    # Font
    objects.append((font_obj, b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>"))

    # Page objects
    for idx in range(page_count):
        page_obj = first_page_obj + idx
        content_obj = first_content_obj + idx
        page_dict = (
            f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 {width} {height}] "
            f"/Resources << /Font << /F1 {font_obj} 0 R >> >> "
            f"/Contents {content_obj} 0 R >>"
        )
        objects.append((page_obj, page_dict.encode("utf-8")))

    # Content objects
    for idx, pg in enumerate(pages):
        objnum = first_content_obj + idx
        stream = content_stream(pg.lines)
        header = f"<< /Length {len(stream)} >>\nstream\n".encode("utf-8")
        footer = b"endstream"
        objects.append((objnum, header + stream + footer))

    # Assemble PDF
    objects.sort(key=lambda x: x[0])
    out = bytearray()
    out.extend(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")

    offsets: dict[int, int] = {}
    for objnum, payload in objects:
        offsets[objnum] = len(out)
        out.extend(f"{objnum} 0 obj\n".encode("utf-8"))
        out.extend(payload)
        out.extend(b"\nendobj\n")

    xref_start = len(out)
    max_obj = max(offsets.keys()) if offsets else 0
    out.extend(f"xref\n0 {max_obj + 1}\n".encode("utf-8"))
    out.extend(b"0000000000 65535 f \n")
    for i in range(1, max_obj + 1):
        off = offsets.get(i, 0)
        out.extend(f"{off:010d} 00000 n \n".encode("utf-8"))
    out.extend(
        (
            f"trailer\n<< /Size {max_obj + 1} /Root 1 0 R >>\n"
            f"startxref\n{xref_start}\n%%EOF\n"
        ).encode("utf-8")
    )
    return bytes(out)

