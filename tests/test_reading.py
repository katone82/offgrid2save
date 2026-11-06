from datetime import date

from billcore.extract import apply_rule, label_regex, split_lines
from billcore.learn import add_builtin_rules, learn_rule, learn_template
from billcore.pipeline import (
    STATUS_IGNORED,
    STATUS_LEARN,
    STATUS_OK,
    STATUS_REVIEW,
    STATUS_UNREADABLE,
    read_bill,
)
from billcore.tokens import normalize

CONFIRMED_NEW = {
    "period_start": "2026-05-01",
    "period_end": "2026-05-31",
    "total_cost": 65.40,
    "consumption_kwh": 1210.5,
    "bill_number": "77/AB-2026",
}


def test_seed_template_reads_enel_but_asks_for_confirmation(enel_bill, enel_template, generic_template):
    reading = read_bill(enel_bill, [enel_template], generic_template)
    assert reading.template_id == "enel_energia"
    assert reading.status == STATUS_REVIEW
    assert reading.values["period_start"] == date(2026, 3, 1)
    assert reading.values["period_end"] == date(2026, 4, 30)
    assert reading.values["total_cost"] == 148.70
    assert reading.values["consumption_kwh"] == 320
    assert reading.values["bill_number"] == "3012345678"
    assert reading.values["issue_date"] == date(2026, 5, 12)
    assert reading.values["consumption_f1"] == 120
    assert reading.values["consumption_f2"] == 80
    assert reading.values["consumption_f3"] == 120
    assert reading.values["cost_energy"] == 78.20
    assert reading.values["cost_taxes"] == 13.00
    assert reading.values["cost_tv"] == 19.00
    assert reading.values["cost_variable"] == 90.00
    assert reading.values["cost_fixed"] == 26.70
    assert reading.issues == []


def test_confirmed_enel_bill_makes_the_next_ones_automatic(enel_bill, enel_template, generic_template):
    first = read_bill(enel_bill, [enel_template], generic_template)
    learned, unlocated = learn_template(
        "Enel Energia", first.values, enel_bill, base=enel_template
    )
    assert unlocated == []
    assert learned["learned"] is True

    next_bill = enel_bill.replace("148,70", "99,10").replace("320 kWh", "210 kWh")
    reading = read_bill(next_bill, [enel_template, learned], generic_template)
    assert reading.status == STATUS_OK
    assert reading.values["total_cost"] == 99.10
    assert reading.values["consumption_kwh"] == 210


def test_spacing_noise_from_pdf_extraction(enel_template, generic_template):
    noisy = (
        "Enel  Energia\n"
        "Periodo   di    fatturazione  01/03/2026   -   30/04/2026\n"
        "Totaleda   pagare     € 10,00\n"
        "Consumo     fatturato    40 kWh\n"
    )
    reading = read_bill(noisy, [enel_template], generic_template)
    assert reading.values["total_cost"] == 10.00
    assert reading.values["consumption_kwh"] == 40
    assert reading.values["period_end"] == date(2026, 4, 30)


def test_new_supplier_goes_to_learning(new_supplier_bill, enel_template, generic_template):
    reading = read_bill(new_supplier_bill, [enel_template], generic_template)
    assert reading.status == STATUS_LEARN
    assert reading.template_id is None


def test_learning_a_new_supplier(new_supplier_bill, enel_template, generic_template):
    learned, unlocated = learn_template("Luce Facile", CONFIRMED_NEW, new_supplier_bill)
    assert unlocated == []
    assert learned["id"] == "luce_facile"

    # Same layout, different month and amounts: it must read on its own.
    next_bill = (
        new_supplier_bill.replace("01/05/2026", "01/06/2026")
        .replace("31/05/2026", "30/06/2026")
        .replace("65,40", "71,15")
        .replace("1.210,5", "980,0")
        .replace("77/AB-2026", "91/AB-2026")
    )
    reading = read_bill(next_bill, [enel_template, learned], generic_template)
    assert reading.status == STATUS_OK
    assert reading.template_id == "luce_facile"
    assert reading.values["period_start"] == date(2026, 6, 1)
    assert reading.values["period_end"] == date(2026, 6, 30)
    assert reading.values["total_cost"] == 71.15
    assert reading.values["consumption_kwh"] == 980
    assert reading.values["bill_number"] == "91/AB-2026"


def test_changed_layout_is_flagged_and_relearned(enel_bill, enel_template, generic_template):
    first = read_bill(enel_bill, [enel_template], generic_template)
    learned, _ = learn_template("Enel Energia", first.values, enel_bill, base=enel_template)

    redesigned = (
        "Enel Energia\n"
        "Fornitura dal 01/05/2026 al 30/06/2026\n"
        "Quanto devi pagare     77,00\n"
        "Hai consumato          150 kWh\n"
    )
    reading = read_bill(redesigned, [learned], generic_template)
    assert reading.status == STATUS_REVIEW

    relearned, unlocated = learn_template(
        "Enel Energia",
        {
            "period_start": "2026-05-01",
            "period_end": "2026-06-30",
            "total_cost": 77.0,
            "consumption_kwh": 150.0,
        },
        redesigned,
        base=learned,
    )
    assert unlocated == []
    assert read_bill(redesigned, [relearned], generic_template).status == STATUS_OK
    # The old layout still works after learning the new one.
    assert read_bill(enel_bill, [relearned], generic_template).status == STATUS_OK


def test_correcting_one_wrong_value_teaches_the_right_label(generic_template):
    text = (
        "Bolletta Acme acme-energia.it\n"
        "Periodo di fatturazione 01/01/2026 - 31/01/2026\n"
        "Totale da pagare 10,00\n"
        "Rata del mese 45,00\n"
        "Consumo fatturato 100 kWh\n"
    )
    wrong = {"period_start": "2026-01-01", "period_end": "2026-01-31", "consumption_kwh": 100.0}
    learned, _ = learn_template("Acme", {**wrong, "total_cost": 10.0}, text)
    corrected, unlocated = learn_template("Acme", {**wrong, "total_cost": 45.0}, text, base=learned)
    assert unlocated == []
    assert read_bill(text, [corrected], generic_template).values["total_cost"] == 45.0


FULL_BILL = (
    "Energia Verde S.p.A.   energiaverde.it\n"
    "Fattura n. 2026/4471 del 03/12/2026\n"
    "Periodo dal 05/11/2026 al 30/11/2026\n"
    "Totale da pagare     41,30 EUR\n"
    "Trasporto e gestione contatore    9,80\n"
    "Imposte e IVA        4,20\n"
    "Spesa dell'energia   12,10\n"
    "Consumo fatturato    52 kWh\n"
    "F1 20 kWh   F2 12 kWh   F3 20 kWh\n"
)
FULL_VALUES = {
    "period_start": "2026-11-05",
    "period_end": "2026-11-30",
    "total_cost": 41.30,
    "consumption_kwh": 52.0,
    "bill_number": "2026/4471",
    "issue_date": "2026-12-03",
    "cost_transport": 9.80,
    "cost_taxes": 4.20,
    "cost_energy": 12.10,
    "consumption_f1": 20.0,
    "consumption_f2": 12.0,
    "consumption_f3": 20.0,
}


def test_every_confirmed_field_is_learned(generic_template):
    # Short words and codes between label and value used to break the label, so
    # the field silently stayed unlearned although it was right there in the text.
    learned, unlocated = learn_template("Energia Verde", FULL_VALUES, FULL_BILL)
    assert unlocated == []

    december = (
        FULL_BILL.replace("9,80", "7,70")
        .replace("4,20", "3,30")
        .replace("12,10", "11,00")
        .replace("2026/4471", "2026/5002")
        .replace("03/12/2026", "04/01/2027")
        .replace("F1 20", "F1 25")
    )
    values = read_bill(december, [learned], generic_template).values
    assert values["cost_transport"] == 7.70
    assert values["cost_taxes"] == 3.30
    assert values["cost_energy"] == 11.00
    assert values["bill_number"] == "2026/5002"
    assert values["issue_date"] == date(2027, 1, 4)
    assert values["consumption_f1"] == 25
    assert values["consumption_f2"] == 12
    assert values["consumption_f3"] == 20


def test_a_known_rule_beats_a_new_one():
    # The real case: F1 read the yearly figure, and correcting it to 2 kWh learned a
    # rule from a chart column that only fitted that one bill. A later rule was right.
    text = (
        "Enel Energia\n"
        "F1 F2 F3 Tot. consumo\n"
        "1.012 kWh 1.326 kWh 1.453 kWh 3.791 kWh\n"
        "Grafico F1 9 8 2\n"
        "F1 F2 F3 Totale energia\n"
        "2 kWh 10 kWh 78 kWh 90 kWh\n"
    )
    base = {
        "id": "x",
        "match": {"any": ["enel energia"]},
        "fields": {
            "consumption_f1": [
                {"label": "f1"},
                {"label": "f1 f2 f3 totale energia", "lookahead": 1, "occurrence": 0},
            ]
        },
    }
    learned, unlocated = learn_template("Enel Energia", {"consumption_f1": 2.0}, text, base=base)
    assert unlocated == []
    assert learned["fields"]["consumption_f1"][0]["label"] == "f1 f2 f3 totale energia"


def test_builtin_rules_reach_a_learned_template_after_it():
    learned = {"id": "x", "learned": True, "fields": {"total_cost": [{"label": "mine"}]}}
    builtin = {
        "id": "x",
        "fields": {
            "total_cost": [{"label": "new"}, {"label": "mine"}],
            "cost_tv": [{"label": "canone"}],
        },
    }
    merged = add_builtin_rules(learned, builtin)
    assert merged["learned"] is True
    assert merged["fields"]["total_cost"] == [{"label": "mine"}, {"label": "new"}]
    assert merged["fields"]["cost_tv"] == [{"label": "canone"}]


def test_rule_from_a_value_under_its_column_header():
    text = (
        "Importo totale        Scadenza\n"
        "   88,20              10/06/2026\n"
    )
    lines = split_lines(text)
    rule = learn_rule("total_cost", 88.20, lines)
    assert rule is not None
    assert apply_rule("total_cost", rule, lines).value == 88.20


def test_value_not_in_the_text_is_reported(new_supplier_bill):
    _, unlocated = learn_template(
        "Luce Facile", {**CONFIRMED_NEW, "total_cost": 999.99}, new_supplier_bill
    )
    assert unlocated == ["total_cost"]


def test_learned_template_holds_no_personal_data(enel_bill, enel_template, generic_template):
    first = read_bill(enel_bill, [enel_template], generic_template)
    learned, _ = learn_template("Enel Energia", first.values, enel_bill, base=enel_template)
    dumped = str(learned).lower()
    assert "mario" not in dumped
    assert "rossi" not in dumped
    assert "it001e" not in dumped
    assert "3012345678" not in dumped


def test_customer_mail_domain_is_not_a_fingerprint():
    text = (
        "Fattura mario@gmail.com  acme-energia.it\n"
        "Periodo di fatturazione 01/01/2026 - 31/01/2026\n"
        "Totale da pagare 10,00\nConsumo fatturato 100 kWh\n"
    )
    learned, _ = learn_template("Nome Diverso", {"total_cost": 10.0}, text)
    assert learned["match"] == {"any": ["acme-energia.it"]}


def test_scanned_bill_is_unreadable_until_typed_in(enel_template, generic_template):
    assert read_bill("  \n ", [enel_template], generic_template).status == STATUS_UNREADABLE
    typed = {
        "period_start": "2026-01-01",
        "period_end": "2026-01-31",
        "total_cost": 50.0,
        "consumption_kwh": 100.0,
    }
    reading = read_bill(" ", [enel_template], generic_template, confirmed=typed)
    assert reading.status == STATUS_OK
    assert reading.values["total_cost"] == 50.0


def test_gas_bill_is_ignored(gas_bill, enel_template, generic_template):
    assert read_bill(gas_bill, [enel_template], generic_template).status == STATUS_IGNORED


def test_fingerprint_is_specific(enel_template, generic_template):
    distributor_mention = "Luce Facile\ne-distribuzione, gruppo Enel\nTotale da pagare 10,00\n"
    reading = read_bill(distributor_mention, [enel_template], generic_template)
    assert reading.template_id is None


def test_label_regex_tolerates_glued_words():
    assert label_regex("totale da pagare").search(normalize("TOTALEDA  PAGARE"))
