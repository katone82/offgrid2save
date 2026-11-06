from datetime import date

from billcore.extract import split_lines
from billcore.tokens import find_amounts, find_codes, find_dates, find_kwh, find_numbers, parse_number


def values(tokens):
    return [t.value for t in tokens]


def test_italian_numbers():
    assert parse_number("1.234,56") == 1234.56
    assert parse_number("1.234") == 1234
    assert parse_number("12,5") == 12.5
    assert parse_number("-12,34") == -12.34
    assert parse_number("12,34-") == -12.34
    assert parse_number("€ 148,70") == 148.70


def test_amounts_need_cents_or_a_euro_sign():
    assert values(find_amounts("Totale € 148,70")) == [148.70]
    assert values(find_amounts("costo 25 euro")) == [25]
    assert values(find_amounts("Potenza 3 kW, lettura 120")) == []
    assert values(find_amounts("credito -12,34 €")) == [-12.34]


def test_numbers_inside_codes_and_dates_are_not_values():
    assert values(find_numbers("POD IT001E12345678 F1 del 12/05/2026")) == []
    assert values(find_numbers("consumo 320 kWh")) == [320]


def test_kwh_prefers_marked_values():
    assert values(find_kwh("Potenza 3 consumo 1.210,5 kWh")) == [1210.5]
    assert values(find_kwh("consumo 320")) == [320]


def test_dates_in_all_formats():
    assert values(find_dates("dal 01/03/2026 al 30.04.26")) == [date(2026, 3, 1), date(2026, 4, 30)]
    assert values(find_dates("emessa il 5 maggio 2026")) == [date(2026, 5, 5)]
    assert values(find_dates("32/13/2026")) == []


def test_month_only_period_uses_the_month_bounds():
    assert values(find_dates("febbraio 2026")) == [date(2026, 2, 1)]
    assert values(find_dates("febbraio 2026", end_of_month=True)) == [date(2026, 2, 28)]


def test_code_does_not_read_a_date():
    assert values(find_codes("n. 3012345678 del 12/05/2026")) == ["3012345678"]
    assert values(find_codes("del 12/05/2026")) == []


def test_ligatures_do_not_shift_positions():
    line = split_lines("Costi ﬁssi    26,70")[0]
    assert "fissi" in line
    assert values(find_amounts(line)) == [26.70]
