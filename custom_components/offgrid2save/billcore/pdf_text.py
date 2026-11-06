"""Extract text from a PDF while keeping its visual columns."""

from __future__ import annotations

import io
import logging

from pypdf import PdfReader

# pypdf logs a warning per font on Enel bills, for an optional dependency that makes
# no difference to the text they yield: they would flood the Home Assistant log.
logging.getLogger("pypdf").setLevel(logging.ERROR)


class UnreadablePdf(Exception):
    """The file is damaged or password protected."""


def pdf_to_text(data: bytes) -> str:
    """Return the text of a PDF, empty when it only contains scanned images."""
    try:
        reader = PdfReader(io.BytesIO(data))
        if reader.is_encrypted and not reader.decrypt(""):
            raise UnreadablePdf("password protected")
        pages = []
        for page in reader.pages:
            pages.append(page.extract_text(extraction_mode="layout") or "")
    except Exception as err:  # noqa: BLE001
        # pypdf raises all sorts of exceptions on malformed files, and bills arrive
        # from outside: whatever one file does must not stop the rest of the folder.
        raise UnreadablePdf(str(err)) from err
    return "\n".join(pages)
