# ☀️ OffGrid2Save

[![HACS Custom](https://img.shields.io/badge/HACS-Custom-41BDF5.svg)](https://www.hacs.xyz/)
[![Home Assistant](https://img.shields.io/badge/Home%20Assistant-2025.4%2B-18BCF2.svg)](https://www.home-assistant.io/)
[![Validate](https://github.com/sitenable/offgrid2save/actions/workflows/validate.yaml/badge.svg)](https://github.com/sitenable/offgrid2save/actions/workflows/validate.yaml)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)

**Quanto ti fa risparmiare davvero il tuo impianto fotovoltaico?** OffGrid2Save legge le tue bollette elettriche in PDF, scarica i dati dell'impianto dal portale Victron VRM e ti mostra in Home Assistant il risparmio mese per mese.

*English summary [at the end of this page](#english).*

![Il riepilogo di OffGrid2Save, con il risparmio totale e il confronto bolletta per bolletta](https://raw.githubusercontent.com/sitenable/offgrid2save/main/docs/riepilogo.jpg)

<sub>Gli screenshot usano bollette e dati inventati.</sub>

## Cosa fa

- 📄 **Legge le bollette PDF:** periodo, consumi, fasce e voci di costo. Tutto in locale, senza AI.
- 🧠 **Impara il formato di ogni fornitore:** confermi la prima bolletta e le successive vengono lette da sole. Se cambi compagnia o cambia il layout, te lo chiede di nuovo.
- 🔌 **Usa i dati reali dell'impianto:** li scarica da Victron VRM, con tutto lo storico, oppure li legge dai sensori di energia di Home Assistant, di qualsiasi marca.
- 🔄 **Si aggiorna da solo:** ogni nuova bolletta scarica i giorni che copre, e ogni notte si aggiunge il giorno appena finito.
- 📊 **Mostra tutto in Home Assistant:** un pannello nella barra laterale, 12 sensori e un evento per le automazioni.

## Installazione con HACS

[HACS](https://www.hacs.xyz/) (Home Assistant Community Store) è lo store della community di Home Assistant: installa le integrazioni create dagli utenti e ti avvisa quando escono aggiornamenti. Se non lo hai ancora, segui la [guida ufficiale](https://www.hacs.xyz/docs/use/).

OffGrid2Save non è ancora nell'elenco predefinito di HACS, quindi va aggiunto come **repository personalizzato**. Bastano pochi clic.

### 1. Aggiungi il repository

Con questo pulsante si apre direttamente il tuo Home Assistant:

[![Apri in HACS](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=sitenable&repository=offgrid2save&category=integration)

<details>
<summary>Oppure a mano</summary>

1. Apri **HACS** dalla barra laterale.
2. Dal menu **⋮** in alto a destra scegli **Repository personalizzati**.
3. Come repository scrivi `https://github.com/sitenable/offgrid2save`.
4. Come tipo scegli **Integrazione** e premi **Aggiungi**.

</details>

### 2. Scarica l'integrazione

In HACS cerca **OffGrid2Save**, aprilo e premi **Scarica**.

### 3. Riavvia Home Assistant

Vai in **Impostazioni → Sistema** e riavvia dal menu in alto a destra. Se usi Docker, va bene anche `docker restart homeassistant`.

### 4. Aggiungi l'integrazione

[![Aggiungi a Home Assistant](https://my.home-assistant.io/badges/config_flow_start.svg)](https://my.home-assistant.io/redirect/config_flow_start/?domain=offgrid2save)

Oppure vai in **Impostazioni → Dispositivi e servizi → Aggiungi integrazione** e cerca **OffGrid2Save**. Se non compare, ricarica la pagina con Ctrl+F5.

### Aggiornamenti

Quando esce una nuova versione, HACS te lo segnala: premi **Aggiorna**, riavvia Home Assistant e ricarica il pannello con Ctrl+F5.

<details>
<summary>Installazione senza HACS</summary>

Copia la cartella `custom_components/offgrid2save` di questo repository dentro `custom_components/` nella configurazione di Home Assistant, poi riavvia e aggiungi l'integrazione. Gli aggiornamenti vanno ripetuti a mano.

</details>

## Configurazione

Pochi passi, modificabili in seguito da **Configura** nella pagina dell'integrazione:

| Passo | Cosa scegli |
|---|---|
| **Cartella** | Dove stanno le bollette. Predefinita: `offgrid2save/bollette` dentro la configurazione di Home Assistant. |
| **Sorgente dei dati** | Portale VRM, consigliato, oppure sensori di Home Assistant. |
| **Accesso** | Il token VRM, oppure i tuoi contatori di energia (kWh). In entrambi i casi, come è collegata la rete. |
| **Prezzi** | Come valorizzare i kWh solari, ed eventuali ricavo per kWh ceduto e prezzo manuale. |

### Il token VRM

Sul [portale VRM](https://vrm.victronenergy.com) vai in **Preferences → Integrations → Access tokens**, crea un token e incollalo nella configurazione. Resta in Home Assistant e viene inviato solo a VRM, per leggere i dati.

### Come è collegata la rete

Questa scelta cambia il significato dei numeri:

| Collegamento | Quando | Cosa cambia |
|---|---|---|
| **La rete entra nell'impianto** | AC-in collegato, ad esempio un sistema ESS | I kWh fatturati vengono confrontati con il prelievo misurato |
| **Separati** | L'impianto alimenta in isola i suoi carichi, la bolletta paga gli altri circuiti | Rete e solare si sommano nel totale della casa |

Con un GX la scelta viene proposta da sola, in base all'uso degli ingressi AC.

<details>
<summary>Usare i sensori di Home Assistant invece di VRM</summary>

Serve un contatore di energia con statistiche a lungo termine per ogni ruolo. Con l'[integrazione Victron GX](https://www.home-assistant.io/integrations/victron_gx/) vengono riconosciuti da soli:

| Ruolo | Contatori |
|---|---|
| Produzione | `Total yield` di ogni SmartSolar |
| Prelievo dalla rete | MultiPlus: `AC-in 1 → AC-out` + `AC-in 1 → inverter` |
| Immissione in rete | MultiPlus: `AC-out → AC-in 1` + `inverter → AC-in 1` |
| Consumo casa | MultiPlus: `AC-in 1 → AC-out` + `inverter → AC-out`, meno `AC-out → AC-in 1` e `AC-out → inverter` |
| Batteria | GX: energia di carica e di scarica |

Con altre marche scegli i tuoi sensori. Le statistiche coprono solo i giorni registrati da Home Assistant.

</details>

## Come si usa

Trascina il PDF nel pannello **OffGrid2Save** oppure copialo nella cartella: viene controllata ogni 5 minuti.

La prima bolletta di ogni fornitore va confermata. Controlli i valori guardando il testo del PDF, con la riga di origine evidenziata, e da quel momento le bollette di quel fornitore vengono lette in automatico.

![La schermata di conferma, con i valori letti accanto al testo della bolletta](https://raw.githubusercontent.com/sitenable/offgrid2save/main/docs/conferma.jpg)

| Stato | Significato | Cosa fare |
|---|---|---|
| ✅ **Letta** | Fornitore conosciuto, valori coerenti | Niente |
| ⚠️ **Da confermare** | Primo uso del template, oppure layout cambiato | Controlla e conferma |
| ❓ **Nuovo fornitore** | Nessun template riconosce il PDF | Controlla, scrivi il nome del fornitore e conferma |
| ✏️ **Da compilare** | Scansione o PDF protetto | Inserisci i valori a mano |
| ➖ **Gas, ignorata** | Bolletta del gas | Niente |

Una bolletta entra nei totali solo dopo la tua conferma, o quella di un template che hai già confermato: una lettura sbagliata altererebbe i confronti senza che tu possa accorgertene.

## Come viene calcolato il risparmio

Solo per il calcolo, si fa finta che l'energia dei pannelli l'abbia fornita il tuo fornitore:

```text
bolletta simulata = costo dell'energia in bolletta + kWh solari × prezzo del fornitore
costo unitario    = bolletta simulata ÷ (kWh della rete + kWh solari)
risparmio         = costo unitario × kWh solari
```

**Esempio:** 50 € di energia in bolletta, 90 kWh dalla rete, 360 kWh solari, quota consumi a 0,24 €/kWh.

```text
bolletta simulata = 50 € + 360 kWh × 0,24 €  = 136,40 €
costo unitario    = 136,40 € ÷ 450 kWh       = 0,303 €/kWh
risparmio         = 0,303 €/kWh × 360 kWh    = 109,12 €
```

- **Prezzo del fornitore:** la quota consumi con le sue imposte. Se una bolletta non la riporta si usa quella dell'ultima che l'aveva e, in ultima istanza, la media, segnalata nel pannello.
- **Costo dell'energia:** il totale senza canone TV e altre partite, che non dipendono dall'energia.
- **kWh solari:** quelli consumati dai carichi, non tutti quelli prodotti: ciò che si perde in batteria non fa risparmiare nulla.
- **"Senza impianto":** è la bolletta reale più i kWh solari al prezzo del fornitore, con le quote fisse invariate. La sua differenza con il pagato è quindi più bassa del risparmio, che attribuisce ai kWh solari anche una parte delle quote fisse.

Nei prezzi puoi scegliere **solo la quota consumi**, per una stima più prudente, oppure impostare un prezzo manuale. La stessa spiegazione, con un esempio sui tuoi numeri, è nella scheda **Configurazione** del pannello.

![La legenda nella scheda Configurazione](https://raw.githubusercontent.com/sitenable/offgrid2save/main/docs/legenda.jpg)

## Sensori e automazioni

I valori in euro e kWh sono disponibili come sensori, da usare in dashboard e automazioni:

| Sensore | Cosa misura |
|---|---|
| Risparmio totale | Somma del risparmio su tutte le bollette |
| Totale pagato / Totale senza impianto | Lo stesso insieme di bollette |
| Costo, risparmio, energia, costo senza impianto dell'ultima bolletta | Valori dell'ultima bolletta |
| Prezzo energia | Costo unitario dell'ultima bolletta |
| Autosufficienza ultima bolletta | Quota di energia coperta dall'impianto |
| Risparmio e autosufficienza dall'ultima bolletta | Periodo non ancora fatturato |
| Bollette da controllare | Quante aspettano la tua conferma |

A ogni nuova bolletta viene emesso l'evento `offgrid2save_bill_processed`. Il servizio `offgrid2save.rescan` controlla subito la cartella.

## Compatibilità

- **Home Assistant:** 2025.4 o successivo, con il recorder attivo.
- **Fornitori:** il template incluso è per **Enel Energia**, provato su bollette reali del mercato libero. Gli altri fornitori si imparano confermando una bolletta.
- **Impianto:** provato su Cerbo GX, MultiPlus-II e SmartSolar. Per chi non ha Victron ci sono i sensori di Home Assistant.

## Limiti noti

- Le scansioni non vengono lette (niente OCR): i valori si inseriscono a mano.
- Le imposte vengono applicate in proporzione: accise e scaglioni sono approssimati.
- Il risparmio è una stima basata sul metodo descritto sopra, non un dato della bolletta.
- I giorni che la sorgente non ha misurato restano fuori. Quella bolletta viene indicata come parziale, e il suo risparmio è un valore minimo.

<details>
<summary>Home Assistant ha corrotto il database?</summary>

Se usi i sensori e il database è stato rinominato in `home-assistant_v2.db.corrupt.*`, spesso le statistiche si possono recuperare senza toccare il database attuale. Dalla cartella di configurazione, con lo script che trovi in `tools/`:

```bash
python3 recover_history.py home-assistant_v2.db.corrupt.XXX > offgrid2save/history.json
```

Vengono tenuti solo i giorni affidabili. Con VRM non serve.

</details>

## Privacy

- Le bollette restano nella tua cartella e non vengono inviate a nessuno. OffGrid2Save salva solo i valori estratti.
- Le uniche richieste verso l'esterno sono quelle a VRM, se lo usi, per leggere i dati del tuo impianto.
- Il testo delle bollette e la conferma sono accessibili solo agli amministratori.
- Il token VRM è salvato nella configurazione di Home Assistant, in chiaro come le altre credenziali, quindi finisce anche nei backup. Trattali come dati riservati.

## Contribuire

Segnalazioni e proposte sono benvenute nelle [issue](https://github.com/sitenable/offgrid2save/issues).

**Un nuovo fornitore?** Basta un template in `custom_components/offgrid2save/templates/`: dopo aver confermato una bolletta trovi il tuo in `offgrid2save/templates/`, nella configurazione di Home Assistant. Contiene solo le etichette stampate vicino ai valori, ma controllalo prima di condividerlo.

> ⚠️ **Non allegare mai una bolletta reale:** contiene nome, indirizzo, POD e codice fiscale. Per le prove in locale usa `samples/bollette/`, che è esclusa da git.

```bash
pip install -r requirements-test.txt
```

```bash
pytest tests
```

La logica in `custom_components/offgrid2save/billcore/` non dipende da Home Assistant e si prova da sola.

## English

OffGrid2Save reads your electricity bills as PDFs, downloads your solar plant's data from Victron VRM or from Home Assistant energy sensors, and shows in Home Assistant how much the plant saves you, month by month. The panel is available in Italian and English. Bills are read locally, with no AI. It learns each supplier's layout from one bill you confirm. The built-in template is for the Italian supplier Enel Energia.

**Install with HACS:** open HACS, go to **⋮ → Custom repositories**, add `https://github.com/sitenable/offgrid2save` as an **Integration**, download **OffGrid2Save**, restart Home Assistant, then add it from **Settings → Devices & services**.

**Savings:** simulated bill = the bill's energy cost + solar kWh at the supplier's consumption charge; unit cost = simulated bill ÷ all kWh (grid + solar); savings = unit cost × solar kWh.

## Licenza

[MIT](LICENSE). Progetto indipendente, non affiliato a Enel né a Victron Energy. I nomi citati appartengono ai rispettivi proprietari.
#   o f f g r i d 2 s a v e  
 