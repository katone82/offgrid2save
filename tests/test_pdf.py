"""End-to-end from real PDF bytes, using a generated PDF."""

from datetime import date

from fpdf import FPDF
import pytest

from billcore.pdf_text import UnreadablePdf, pdf_to_text
from billcore.pipeline import STATUS_REVIEW, read_bill


def make_pdf(rows: list[tuple[str, str]]) -> bytes:
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Helvetica", size=10)
    for left, right in rows:
        pdf.cell(120, 6, left)
        pdf.cell(60, 6, right, new_x="LMARGIN", new_y="NEXT")
    return bytes(pdf.output())


ROWS = [
    ("Enel Energia S.p.A.", "www.enel.it"),
    ("Bolletta n. 3012345678 del 12/05/2026", ""),
    ("Periodo di fatturazione", "01/03/2026 - 30/04/2026"),
    ("Totale da pagare", "EUR 148,70"),
    ("Spesa per la materia energia", "78,20"),
    ("Consumo fatturato", "320 kWh"),
    ("Consumo fatturato F1 F2 F3", ""),
]


def test_generated_pdf_reads_through_the_whole_chain(enel_template, generic_template):
    text = pdf_to_text(make_pdf(ROWS))
    reading = read_bill(text, [enel_template], generic_template)
    assert reading.status == STATUS_REVIEW
    assert reading.values["total_cost"] == 148.70
    assert reading.values["consumption_kwh"] == 320
    assert reading.values["period_start"] == date(2026, 3, 1)
    assert reading.values["period_end"] == date(2026, 4, 30)


def test_image_only_pdf_has_no_text():
    pdf = FPDF()
    pdf.add_page()
    assert pdf_to_text(bytes(pdf.output())).strip() == ""


def test_garbage_is_reported_not_raised_as_anything_else():
    with pytest.raises(UnreadablePdf):
        pdf_to_text(b"%PDF-1.7 this is not really a pdf")
    with pytest.raises(UnreadablePdf):
        pdf_to_text(b"not a pdf at all")
