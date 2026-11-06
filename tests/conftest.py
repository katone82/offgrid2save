"""Test helpers: billcore is importable without Home Assistant."""

from __future__ import annotations

import json
from pathlib import Path
import sys

import pytest

PACKAGE = Path(__file__).parent.parent / "custom_components" / "offgrid2save"
sys.path.insert(0, str(PACKAGE))


@pytest.fixture
def enel_template() -> dict:
    return json.loads((PACKAGE / "templates" / "enel_energia.json").read_text("utf-8"))


@pytest.fixture
def generic_template() -> dict:
    return json.loads((PACKAGE / "templates" / "generic_it.json").read_text("utf-8"))


# Synthetic bills: invented numbers and people, shaped after the published Enel
# section names. Not a copy of a real document.
ENEL_BILL = """
Enel Energia S.p.A. - Mercato libero                         www.enel.it
Bolletta n. 3012345678 del 12/05/2026
Intestatario: Mario Rossi    Codice POD IT001E12345678
Periodo di fatturazione: 01/03/2026 - 30/04/2026
                                   Scontrino dell'energia
Totale da pagare                                        € 148,70
Spesa per la materia energia                            78,20
Spesa per il trasporto e la gestione del contatore      24,10
Spesa per oneri di sistema                              14,40
Totale imposte e IVA                                    13,00
Canone di abbonamento alla televisione                  19,00
Costi variabili                                         90,00
Costi fissi                                             26,70
Consumo fatturato                                       320 kWh
F1 120 kWh     F2 80 kWh     F3 120 kWh
"""

NEW_SUPPLIER_BILL = """
Luce Facile S.r.l.                                luce-facile.it
Documento 77/AB-2026
Competenza: dal 01/05/2026 al 31/05/2026
Importo dovuto                                     65,40 euro
Energia prelevata                                  1.210,5 kWh
"""

GAS_BILL = """
Enel Energia S.p.A.
Codice PDR 01234567890123
Periodo di fatturazione: 01/03/2026 - 30/04/2026
Consumo fatturato 120 Smc
Totale da pagare 95,00
"""


@pytest.fixture
def enel_bill() -> str:
    return ENEL_BILL


@pytest.fixture
def new_supplier_bill() -> str:
    return NEW_SUPPLIER_BILL


@pytest.fixture
def gas_bill() -> str:
    return GAS_BILL
