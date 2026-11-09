from __future__ import annotations

import io

from pypdf import PdfReader, PdfWriter


def _escape_pdf_text(text: str) -> bytes:
    escaped = text.replace("\\", "\\\\").replace("(", "\\(").replace(
        ")", "\\)"
    )
    return escaped.encode("latin-1", errors="replace")


def build_pdf(pages: list[str]) -> bytes:
    objects: list[bytes] = []

    def add(obj: bytes) -> int:
        objects.append(obj)
        return len(objects)

    add(b"")  # catalog
    add(b"")  # pages tree
    font_num = add(
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>"
    )

    page_refs: list[str] = []
    for text in pages:
        stream = (
            b"BT /F1 12 Tf 72 720 Td (" + _escape_pdf_text(text) + b") Tj ET"
        )
        content_num = len(objects) + 1
        objects.append(
            b"<< /Length "
            + str(len(stream)).encode()
            + b" >>\nstream\n"
            + stream
            + b"\nendstream"
        )
        page_num = len(objects) + 1
        objects.append(
            b"<< /Type /Page /Parent 2 0 R "
            b"/MediaBox [0 0 612 792] "
            b"/Resources << /Font << /F1 "
            + str(font_num).encode()
            + b" 0 R >> >> "
            b"/Contents "
            + str(content_num).encode()
            + b" 0 R >>"
        )
        page_refs.append(f"{page_num} 0 R")

    objects[0] = b"<< /Type /Catalog /Pages 2 0 R >>"
    kids = "[ " + " ".join(page_refs) + " ]"
    objects[1] = (
        b"<< /Type /Pages /Kids "
        + kids.encode()
        + b" /Count "
        + str(len(pages)).encode()
        + b" >>"
    )

    output = bytearray(b"%PDF-1.4\n")
    offsets = [0]
    for index, obj in enumerate(objects, start=1):
        offsets.append(len(output))
        output += f"{index} 0 obj\n".encode()
        output += obj + b"\nendobj\n"

    xref = len(output)
    output += f"xref\n0 {len(objects) + 1}\n".encode()
    output += b"0000000000 65535 f \n"
    for offset in offsets[1:]:
        output += f"{offset:010d} 00000 n \n".encode()
    output += (
        f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\n"
        f"startxref\n{xref}\n%%EOF\n"
    ).encode()
    return bytes(output)


def build_encrypted_pdf(
    pages: list[str],
    *,
    password: str = "secret",
) -> bytes:
    reader = PdfReader(io.BytesIO(build_pdf(pages)))
    writer = PdfWriter()
    for page in reader.pages:
        writer.add_page(page)
    writer.encrypt(password)
    buffer = io.BytesIO()
    writer.write(buffer)
    return buffer.getvalue()
