from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable
import zlib

from PIL import Image


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


@dataclass(frozen=True)
class PdfImage:
    name: str
    width: int
    height: int
    data: bytes


def _pil_to_pdf_image(name: str, img: Image.Image) -> PdfImage:
    # Composite alpha onto white so the PDF doesn't need transparency support.
    if img.mode in ("RGBA", "LA") or ("transparency" in img.info):
        base = Image.new("RGB", img.size, (255, 255, 255))
        rgba = img.convert("RGBA")
        base.paste(rgba, mask=rgba.split()[-1])
        rgb = base
    else:
        rgb = img.convert("RGB")
    width, height = rgb.size
    raw = rgb.tobytes()
    compressed = zlib.compress(raw)
    return PdfImage(name=name, width=width, height=height, data=compressed)


def build_validation_pdf(
    *,
    text_lines: list[str],
    watermark: Image.Image | None = None,
    logo: Image.Image | None = None,
    qr: Image.Image | None = None,
    font_size: int = 10,
) -> bytes:
    # A4 portrait points
    page_w = 595
    page_h = 842

    font_obj = 3
    objnum = 1

    images: list[PdfImage] = []
    if watermark is not None:
        images.append(_pil_to_pdf_image("WM", watermark))
    if logo is not None:
        images.append(_pil_to_pdf_image("LG", logo))
    if qr is not None:
        images.append(_pil_to_pdf_image("QR", qr))

    # object numbers
    catalog_obj = 1
    pages_obj = 2
    font_obj = 3
    first_img_obj = 4
    page_obj = first_img_obj + len(images)
    content_obj = page_obj + 1

    def image_obj_payload(p: PdfImage) -> bytes:
        header = (
            f"<< /Type /XObject /Subtype /Image /Width {p.width} /Height {p.height} "
            f"/ColorSpace /DeviceRGB /BitsPerComponent 8 /Filter /FlateDecode /Length {len(p.data)} >>\n"
            "stream\n"
        ).encode("utf-8")
        return header + p.data + b"\nendstream"

    # Build content stream with images + text
    content_parts: list[str] = []

    def draw_image(img: PdfImage, x: int, y: int, w: int, h: int):
        content_parts.append("q")
        content_parts.append(f"{w} 0 0 {h} {x} {y} cm")
        content_parts.append(f"/{img.name} Do")
        content_parts.append("Q")

    # Watermark: centered, large, lightened (caller should pre-lighten)
    if watermark is not None:
        wm = next(i for i in images if i.name == "WM")
        target = 420
        x = int((page_w - target) / 2)
        y = int((page_h - target) / 2) - 20
        draw_image(wm, x, y, target, target)

    # Header logo: top center
    if logo is not None:
        lg = next(i for i in images if i.name == "LG")
        size = 54
        x = int((page_w - size) / 2)
        y = page_h - 92
        draw_image(lg, x, y, size, size)

    # QR: top right
    if qr is not None:
        qi = next(i for i in images if i.name == "QR")
        size = 84
        x = page_w - 44 - size
        y = page_h - 120
        draw_image(qi, x, y, size, size)

    def _estimate_text_width(text: str) -> int:
        # Rough Helvetica width estimate (good enough for highlight background sizing)
        return int(len(str(text or '')) * font_size * 0.55) + 6

    def _extract_highlights(text_lines: list[str]):
        ok_prefix = "__VALID_OK__"
        bad_prefix = "__VALID_BAD__"
        highlights: list[tuple[int, tuple[float, float, float], tuple[float, float, float], int]] = []
        cleaned: list[str] = []
        for idx, ln in enumerate(text_lines):
            s = str(ln or "")
            if s.startswith(ok_prefix):
                label = s[len(ok_prefix) :]
                cleaned.append(label)
                highlights.append((idx, (0.85, 1.0, 0.85), (0.0, 0.55, 0.0), _estimate_text_width(label)))
                continue
            if s.startswith(bad_prefix):
                label = s[len(bad_prefix) :]
                cleaned.append(label)
                highlights.append((idx, (1.0, 0.88, 0.88), (0.7, 0.0, 0.0), _estimate_text_width(label)))
                continue
            cleaned.append(s)
        return cleaned, highlights

    text_lines, highlights = _extract_highlights(text_lines)

    # Text block
    left = 44
    top = page_h - 150
    leading = int(max(12, round(font_size * 1.35)))

    # Highlight rectangles (draw before text so it appears behind)
    rect_h = font_size + 6
    max_w = page_w - left - 44
    for idx, fill_rgb, stroke_rgb, w_est in highlights:
        rect_w = min(max_w, max(40, w_est))
        rect_x = left - 2
        rect_y = int(top - (idx * leading) - font_size - 2)
        content_parts.append("q")
        content_parts.append(f"{fill_rgb[0]} {fill_rgb[1]} {fill_rgb[2]} rg")
        content_parts.append(f"{stroke_rgb[0]} {stroke_rgb[1]} {stroke_rgb[2]} RG")
        content_parts.append("1 w")
        content_parts.append(f"{rect_x} {rect_y} {rect_w} {rect_h} re")
        content_parts.append("B")
        content_parts.append("Q")

    content_parts.append("BT")
    content_parts.append(f"/F1 {font_size} Tf")
    content_parts.append(f"{left} {top} Td")
    content_parts.append(f"{leading} TL")
    for ln in text_lines:
        esc = _escape_pdf_text(ln)
        content_parts.append(f"({esc}) Tj")
        content_parts.append("T*")
    content_parts.append("ET")

    content_stream = ("\n".join(content_parts) + "\n").encode("utf-8")

    # Objects
    objects: list[tuple[int, bytes]] = []
    objects.append((catalog_obj, f"<< /Type /Catalog /Pages {pages_obj} 0 R >>".encode("utf-8")))
    objects.append((pages_obj, f"<< /Type /Pages /Kids [ {page_obj} 0 R ] /Count 1 >>".encode("utf-8")))
    objects.append((font_obj, b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>"))

    # image objects
    for idx, img in enumerate(images):
        objects.append((first_img_obj + idx, image_obj_payload(img)))

    # page resources include images
    xobj_parts = []
    for idx, img in enumerate(images):
        xobj_parts.append(f"/{img.name} {first_img_obj + idx} 0 R")
    xobj = " ".join(xobj_parts)
    res = f"<< /Font << /F1 {font_obj} 0 R >>"
    if xobj:
        res += f" /XObject << {xobj} >>"
    res += " >>"

    page_dict = (
        f"<< /Type /Page /Parent {pages_obj} 0 R /MediaBox [0 0 {page_w} {page_h}] "
        f"/Resources {res} /Contents {content_obj} 0 R >>"
    )
    objects.append((page_obj, page_dict.encode("utf-8")))

    objects.append(
        (
            content_obj,
            f"<< /Length {len(content_stream)} >>\nstream\n".encode("utf-8")
            + content_stream
            + b"endstream",
        )
    )

    # Assemble
    objects.sort(key=lambda x: x[0])
    out = bytearray()
    out.extend(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")

    offsets: dict[int, int] = {}
    for on, payload in objects:
        offsets[on] = len(out)
        out.extend(f"{on} 0 obj\n".encode("utf-8"))
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
            f"trailer\n<< /Size {max_obj + 1} /Root {catalog_obj} 0 R >>\n"
            f"startxref\n{xref_start}\n%%EOF\n"
        ).encode("utf-8")
    )
    return bytes(out)


def build_validation_pdf_multi(
    *,
    pages_lines: list[list[str]],
    watermark: Image.Image | None = None,
    logo: Image.Image | None = None,
    qr: Image.Image | None = None,
    font_size: int = 10,
    header_each_page: bool = True,
) -> bytes:
    if not pages_lines:
        pages_lines = [[]]

    # A4 portrait points
    page_w = 595
    page_h = 842

    catalog_obj = 1
    pages_obj = 2
    font_obj = 3

    images: list[PdfImage] = []
    if watermark is not None:
        images.append(_pil_to_pdf_image("WM", watermark))
    if logo is not None:
        images.append(_pil_to_pdf_image("LG", logo))
    if qr is not None:
        images.append(_pil_to_pdf_image("QR", qr))

    first_img_obj = 4
    first_page_obj = first_img_obj + len(images)
    first_content_obj = first_page_obj + len(pages_lines)

    def image_obj_payload(p: PdfImage) -> bytes:
        header = (
            f"<< /Type /XObject /Subtype /Image /Width {p.width} /Height {p.height} "
            f"/ColorSpace /DeviceRGB /BitsPerComponent 8 /Filter /FlateDecode /Length {len(p.data)} >>\n"
            "stream\n"
        ).encode("utf-8")
        return header + p.data + b"\nendstream"

    def build_content(page_idx: int, text_lines: list[str]) -> bytes:
        parts: list[str] = []

        def estimate_text_width(text: str) -> int:
            return int(len(str(text or '')) * font_size * 0.55) + 6

        def extract_highlights(lines: list[str]):
            ok_prefix = "__VALID_OK__"
            bad_prefix = "__VALID_BAD__"
            highlights_local: list[tuple[int, tuple[float, float, float], tuple[float, float, float], int]] = []
            cleaned_local: list[str] = []
            for idx, ln in enumerate(lines):
                s = str(ln or "")
                if s.startswith(ok_prefix):
                    label = s[len(ok_prefix) :]
                    cleaned_local.append(label)
                    highlights_local.append((idx, (0.85, 1.0, 0.85), (0.0, 0.55, 0.0), estimate_text_width(label)))
                    continue
                if s.startswith(bad_prefix):
                    label = s[len(bad_prefix) :]
                    cleaned_local.append(label)
                    highlights_local.append((idx, (1.0, 0.88, 0.88), (0.7, 0.0, 0.0), estimate_text_width(label)))
                    continue
                cleaned_local.append(s)
            return cleaned_local, highlights_local

        def draw_image(img: PdfImage, x: int, y: int, w: int, h: int):
            parts.append("q")
            parts.append(f"{w} 0 0 {h} {x} {y} cm")
            parts.append(f"/{img.name} Do")
            parts.append("Q")

        if watermark is not None:
            wm = next(i for i in images if i.name == "WM")
            target = 420
            x = int((page_w - target) / 2)
            y = int((page_h - target) / 2) - 20
            draw_image(wm, x, y, target, target)

        show_header = header_each_page or page_idx == 0
        if show_header and logo is not None:
            lg = next(i for i in images if i.name == "LG")
            size = 54
            x = int((page_w - size) / 2)
            y = page_h - 92
            draw_image(lg, x, y, size, size)

        if show_header and qr is not None:
            qi = next(i for i in images if i.name == "QR")
            size = 84
            x = page_w - 44 - size
            y = page_h - 120
            draw_image(qi, x, y, size, size)

        left = 44
        top = page_h - 150
        leading = int(max(12, round(font_size * 1.35)))

        text_lines, highlights_local = extract_highlights(text_lines)

        # Highlight rectangles (draw before text so it appears behind)
        rect_h = font_size + 6
        max_w = page_w - left - 44
        for idx, fill_rgb, stroke_rgb, w_est in highlights_local:
            rect_w = min(max_w, max(40, w_est))
            rect_x = left - 2
            rect_y = int(top - (idx * leading) - font_size - 2)
            parts.append("q")
            parts.append(f"{fill_rgb[0]} {fill_rgb[1]} {fill_rgb[2]} rg")
            parts.append(f"{stroke_rgb[0]} {stroke_rgb[1]} {stroke_rgb[2]} RG")
            parts.append("1 w")
            parts.append(f"{rect_x} {rect_y} {rect_w} {rect_h} re")
            parts.append("B")
            parts.append("Q")

        parts.append("BT")
        parts.append(f"/F1 {font_size} Tf")
        parts.append(f"{left} {top} Td")
        parts.append(f"{leading} TL")
        for ln in text_lines:
            esc = _escape_pdf_text(ln)
            parts.append(f"({esc}) Tj")
            parts.append("T*")
        parts.append("ET")
        return ("\n".join(parts) + "\n").encode("utf-8")

    objects: list[tuple[int, bytes]] = []
    objects.append((catalog_obj, f"<< /Type /Catalog /Pages {pages_obj} 0 R >>".encode("utf-8")))

    kids = " ".join([f"{first_page_obj + i} 0 R" for i in range(len(pages_lines))])
    objects.append((pages_obj, f"<< /Type /Pages /Kids [ {kids} ] /Count {len(pages_lines)} >>".encode("utf-8")))
    objects.append((font_obj, b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>"))

    for idx, img in enumerate(images):
        objects.append((first_img_obj + idx, image_obj_payload(img)))

    xobj_parts = []
    for idx, img in enumerate(images):
        xobj_parts.append(f"/{img.name} {first_img_obj + idx} 0 R")
    xobj = " ".join(xobj_parts)
    res = f"<< /Font << /F1 {font_obj} 0 R >>"
    if xobj:
        res += f" /XObject << {xobj} >>"
    res += " >>"

    # page + content objs
    for i, lines in enumerate(pages_lines):
        page_obj = first_page_obj + i
        content_obj = first_content_obj + i
        page_dict = (
            f"<< /Type /Page /Parent {pages_obj} 0 R /MediaBox [0 0 {page_w} {page_h}] "
            f"/Resources {res} /Contents {content_obj} 0 R >>"
        )
        objects.append((page_obj, page_dict.encode("utf-8")))

        stream = build_content(i, lines)
        objects.append(
            (
                content_obj,
                f"<< /Length {len(stream)} >>\nstream\n".encode("utf-8") + stream + b"endstream",
            )
        )

    objects.sort(key=lambda x: x[0])
    out = bytearray()
    out.extend(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")

    offsets: dict[int, int] = {}
    for on, payload in objects:
        offsets[on] = len(out)
        out.extend(f"{on} 0 obj\n".encode("utf-8"))
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
            f"trailer\n<< /Size {max_obj + 1} /Root {catalog_obj} 0 R >>\n"
            f"startxref\n{xref_start}\n%%EOF\n"
        ).encode("utf-8")
    )
    return bytes(out)
