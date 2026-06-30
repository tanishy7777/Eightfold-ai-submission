#!/usr/bin/env python3
"""Render a plain-text resume into a minimal, text-extractable PDF.

Stdlib-only (no reportlab/fpdf) so the sample PDF fixture is regenerable on any
machine. Produces a single-font, single-column PDF whose text `pypdf` can pull
back out line-for-line — exactly the "clean, single-column prose" the
ResumeAdapter targets.

The resume text lives here (DEFAULT_LINES) so this script is the single source
of truth for the fixture; there is deliberately no parallel .md/.txt in
data/samples/ that the pipeline's source sniffer would double-count as a second
resume under `--input`.

Usage:
    python data/samples/make_resume_pdf.py                 # -> resume_jane.pdf
    python data/samples/make_resume_pdf.py out.pdf         # custom output path
    python data/samples/make_resume_pdf.py in.txt out.pdf  # render a text file
"""

from __future__ import annotations

import sys
from pathlib import Path

DEFAULT_LINES = [
    "Jane Doe",
    "Senior Software Engineer",
    "",
    "jane.doe@example.com | +1 (415) 555-0142",
    "github.com/janedoe | linkedin.com/in/janedoe",
    "San Francisco, CA",
    "",
    "SKILLS",
    "Python, JavaScript, React, PostgreSQL, Docker",
    "",
    "EXPERIENCE",
    "Senior Software Engineer, Acme Corp (Jan 2021 - Present)",
    "Software Engineer, Globex (Summer 2018 - Dec 2020)",
    "",
    "EDUCATION",
    "B.S. Computer Science, MIT, 2018",
]


def _escape(text: str) -> str:
    """Escape the three characters that are special inside a PDF string."""
    return text.replace("\\", r"\\").replace("(", r"\(").replace(")", r"\)")


def text_to_pdf(lines: list[str], font_size: int = 11, leading: int = 16,
                top: int = 760, left: int = 60) -> bytes:
    """Lay each input line on its own row of a US-Letter page (612x792 pt)."""
    parts = [f"BT /F1 {font_size} Tf {leading} TL {left} {top} Td"]
    for i, line in enumerate(lines):
        if i:
            parts.append("T*")              # advance one line (uses TL leading)
        parts.append(f"({_escape(line)}) Tj")
    parts.append("ET")
    content = "\n".join(parts).encode("latin-1", "replace")

    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
        b"/Resources << /Font << /F1 5 0 R >> >> /Contents 4 0 R >>",
        b"<< /Length %d >>\nstream\n%s\nendstream" % (len(content), content),
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]

    out = bytearray(b"%PDF-1.4\n")
    offsets = []
    for i, body in enumerate(objects, start=1):
        offsets.append(len(out))
        out += b"%d 0 obj\n" % i + body + b"\nendobj\n"

    xref_pos = len(out)
    out += b"xref\n0 %d\n" % (len(objects) + 1)
    out += b"0000000000 65535 f \n"
    for off in offsets:
        out += b"%010d 00000 n \n" % off
    out += (b"trailer\n<< /Size %d /Root 1 0 R >>\nstartxref\n%d\n%%%%EOF\n"
            % (len(objects) + 1, xref_pos))
    return bytes(out)


def main() -> None:
    args = sys.argv[1:]
    here = Path(__file__).resolve().parent
    if len(args) == 0:
        lines, dst = DEFAULT_LINES, here / "resume_jane.pdf"
    elif len(args) == 1:
        lines, dst = DEFAULT_LINES, Path(args[0])
    elif len(args) == 2:
        lines = Path(args[0]).read_text(encoding="utf-8").splitlines()
        dst = Path(args[1])
    else:
        sys.exit("usage: make_resume_pdf.py [<input.txt>] [<output.pdf>]")
    dst.write_bytes(text_to_pdf(lines))
    print(f"wrote {dst} ({len(lines)} lines)")


if __name__ == "__main__":
    main()
