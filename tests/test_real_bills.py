"""Checks on real bills in samples/bollette, kept out of git: skipped when there are none.

Only totals and consistency are asserted here, so no figure from a real bill ends up
in the repository.
"""

from pathlib import Path

import pytest

from billcore.extract import split_lines
from billcore.learn import learn_template
from billcore.pdf_text import pdf_to_text
from billcore.pipeline import STATUS_OK, STATUS_REVIEW, read_bill

SAMPLES = sorted((Path(__file__).parent.parent / "samples" / "bollette").glob("*.pdf"))
PARTS = (
    "cost_energy", "cost_transport", "cost_system", "cost_recalc",
    "cost_other", "cost_bonus", "cost_taxes", "cost_tv",
)
pytestmark = pytest.mark.skipif(not SAMPLES, reason="no real bills in samples/bollette")


@pytest.fixture(params=SAMPLES, ids=lambda path: path.stem[-6:])
def reading(request, enel_template, generic_template):
    text = pdf_to_text(request.param.read_bytes())
    assert split_lines(text)
    return read_bill(text, [enel_template], generic_template)


def test_enel_template_recognizes_it_and_finds_no_inconsistency(reading):
    assert reading.template_id == "enel_energia"
    assert reading.status == STATUS_REVIEW  # waits for the first confirmation, nothing more
    assert reading.issues == []


def test_cost_items_add_up_to_the_total(reading):
    parts = sum(reading.values.get(key) or 0 for key in PARTS)
    assert parts == pytest.approx(reading.values["total_cost"], abs=0.02)


def test_variable_and_fixed_costs_match_the_detailed_items(reading):
    values = reading.values
    detail = values["cost_energy"] + values["cost_transport"] + values["cost_system"]
    assert values["cost_variable"] + values["cost_fixed"] == pytest.approx(detail, abs=0.02)


@pytest.mark.skipif(len(SAMPLES) < 2, reason="needs at least two real bills")
@pytest.mark.parametrize("teacher", range(len(SAMPLES)), ids=lambda i: f"from_{SAMPLES[i].stem[-6:]}")
def test_what_is_learned_from_one_bill_reads_all_the_others(teacher, enel_template, generic_template):
    # The whole point of learning: confirming one bill must make the others automatic.
    texts = [pdf_to_text(path.read_bytes()) for path in SAMPLES]
    first = read_bill(texts[teacher], [enel_template], generic_template)
    learned, unlocated = learn_template("Enel Energia", first.values, texts[teacher], base=enel_template)
    assert unlocated == []
    for text in texts:
        seed = read_bill(text, [enel_template], generic_template).values
        reading = read_bill(text, [learned], generic_template)
        assert reading.status == STATUS_OK
        assert reading.issues == []
        assert reading.values == seed


def test_bill_number_and_issue_date_are_found(reading):
    assert reading.values["bill_number"]
    assert reading.values["issue_date"] > reading.values["period_end"]


def test_time_bands_are_those_of_the_period(reading):
    values = reading.values
    bands = values["consumption_f1"] + values["consumption_f2"] + values["consumption_f3"]
    assert bands == pytest.approx(values["consumption_kwh"], abs=1.5)
