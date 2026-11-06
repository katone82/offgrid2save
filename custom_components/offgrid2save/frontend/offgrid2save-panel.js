// OffGrid2Save sidebar panel. Plain web component: nothing to build, nothing to install.
// Anything coming from a bill passes through esc(): PDFs arrive from outside and
// this page runs with the session of a Home Assistant administrator.

const FIELD_GROUPS = [
  { key: "main", open: true, fields: [
    ["period_start", "date"], ["period_end", "date"],
    ["total_cost", "eur"], ["consumption_kwh", "kwh"],
  ]},
  { key: "costs", open: true, fields: [
    ["cost_variable", "eur"], ["cost_fixed", "eur"],
    ["cost_energy", "eur"], ["cost_transport", "eur"], ["cost_system", "eur"],
    ["cost_taxes", "eur"], ["cost_tv", "eur"],
    ["cost_recalc", "eur"], ["cost_other", "eur"], ["cost_bonus", "eur"],
  ]},
  { key: "more", open: false, fields: [
    ["bill_number", "text"], ["issue_date", "date"],
    ["consumption_f1", "kwh"], ["consumption_f2", "kwh"], ["consumption_f3", "kwh"],
  ]},
];
const REQUIRED = ["period_start", "period_end", "total_cost", "consumption_kwh"];
const POLL_MS = 60000;
const METER_DELTA_WARN_PCT = 15;
const METER_DELTA_WARN_KWH = 5;

const STRINGS = {
  it: {
    tab_overview: "Riepilogo", tab_bills: "Bollette", tab_setup: "Configurazione",
    hero: "Risparmio totale con l'impianto",
    hero_estimated: (d) => `Risparmio stimato dal ${d}`,
    hero_estimated_sub: "dai dati dell'impianto, al prezzo dell'ultima bolletta",
    no_overlap: (bills, plant) => `Le bollette caricate arrivano al ${bills}, i dati dell'impianto partono dal ${plant}: non hanno giorni in comune, quindi il confronto bolletta per bolletta non è ancora possibile. Comparirà con la prossima bolletta.`,
    plant_produced: "Prodotti dall'impianto", plant_consumed: "Consumati dai carichi dell'impianto",
    plant_since: (d, n) => `dal ${d}, ${n} giorni misurati`,
    hero_sub: (n) => `calcolato su ${n} ${n === 1 ? "bolletta" : "bollette"}`,
    paid: "Pagato in bolletta", without: "Senza impianto avresti pagato",
    self_suff: "Autosufficienza ultima bolletta",
    current: "Periodo non ancora fatturato", current_sub: (d) => `${d} ${d === 1 ? "giorno" : "giorni"} dopo l'ultima bolletta`,
    chart_cost: "Quanto hai pagato e quanto hai risparmiato", chart_energy: "Da dove arriva l'energia consumata",
    series_paid: "Pagato", series_saved: "Risparmiato", series_grid: "Dalla rete", series_plant: "Dall'impianto",
    one_bill: "I grafici compaiono dalla seconda bolletta.",
    table: "Bolletta per bolletta",
    th_period: "Periodo", th_supplier: "Fornitore", th_billed: "Dalla rete", th_meter: "Rete misurata",
    th_delta: "Differenza", th_consumed: "Consumati", th_plant_loads: "Dall'impianto", th_home: "Totale mese",
    th_price_unit: "€/kWh unitario", series_total: "Totale",
    legend_title: "Come si calcola il risparmio",
    legend_steps: [
      "Bolletta simulata: costo dell'energia in bolletta + kWh solari di VRM al prezzo del fornitore, come se li avesse forniti lui.",
      "Costo unitario: bolletta simulata ÷ tutti i kWh del periodo (rete + solare).",
      "Risparmio: costo unitario × kWh solari.",
    ],
    legend_notes: "Prezzo del fornitore: quota consumi con le sue imposte. Canone TV e altre partite esclusi. \"Senza impianto\" = bolletta reale + kWh solari a quel prezzo: le quote fisse non cambiano, quindi la differenza con il pagato è più bassa del risparmio.",
    legend_example: (p, cost, kwh, price, grid, unit, saved) => `Esempio, ${p}: (${cost} € + ${kwh} kWh × ${price} €) ÷ (${grid} + ${kwh}) kWh = ${unit} €/kWh; × ${kwh} kWh = ${saved} € di risparmio.`,
    legend_variable: "Risparmio = kWh solari × quota consumi con le sue imposte. Le quote fisse restano fuori, perché si pagano comunque.",
    legend_manual: "È impostato un prezzo manuale: risparmio = kWh solari × quel prezzo.",
    setup_layout: "Collegamento alla rete",
    setup_vrm: "Portale VRM, impianto", setup_vrm_download: "Ultimo download",
    vrm_auth_error: "VRM ha rifiutato il token di accesso: i nuovi dati dell'impianto non vengono scaricati. Aggiorna il token nelle opzioni dell'integrazione.",
    vrm_unreachable: "VRM non è raggiungibile in questo momento: i conti usano i dati già scaricati e riprovo al prossimo aggiornamento.",
    layout_through_plant: "La rete entra nell'impianto e l'impianto alimenta la casa.",
    layout_separate: "Separati: l'impianto alimenta i suoi carichi in isola, la bolletta paga gli altri circuiti.", th_pv: "Prodotti", th_self: "Autosuff.",
    th_paid: "Pagato", th_without: "Senza impianto", th_saved: "Risparmio", th_price: "€/kWh",
    no_measure: "nessun dato", partial: (p) => `dati su ${p}% del periodo`,
    superseded: "sostituita da una bolletta più recente", overlapping: "periodo sovrapposto a un'altra bolletta",
    review_banner: (n) => `${n} ${n === 1 ? "bolletta aspetta" : "bollette aspettano"} la tua conferma`,
    review_open: "Controlla",
    empty_title: "Carica la prima bolletta",
    empty_text: "Trascina qui un PDF o copialo nella cartella delle bollette. La prima bolletta di ogni fornitore va confermata: da lì in poi la lettura è automatica.",
    price_warn: "Su alcune bollette il prezzo al kWh è una media che include i costi fissi, quindi il risparmio risulta sovrastimato. Indica un prezzo in Configurazione per correggerlo.",
    upload: "Carica PDF", uploading: "Caricamento…", rescan: "Controlla la cartella",
    drop: "Trascina qui le bollette in PDF", duplicate: "Questa bolletta è già presente.",
    upload_failed: "Caricamento non riuscito", admin_only: "Solo un amministratore può caricare e confermare le bollette.",
    th_file: "File", th_status: "Stato", th_total: "Totale", review: "Controlla", edit: "Correggi",
    status_ok: "Letta", status_needs_review: "Da confermare", status_needs_learning: "Nuovo fornitore",
    status_unreadable: "Da compilare", status_ignored: "Gas, ignorata",
    review_title: "Controlla i valori letti",
    review_help: "Correggi ciò che non torna guardando il testo a destra. Confermando, OffGrid2Save impara dove si trovano questi valori e leggerà da solo le prossime bollette di questo fornitore.",
    review_unreadable: "Questo PDF non contiene testo (scansione o file protetto). Puoi inserire i valori a mano: valgono solo per questa bolletta.",
    supplier: "Nome del fornitore, come stampato in bolletta",
    group_main: "Dati essenziali", group_costs: "Voci di costo (facoltative)", group_more: "Altri dati (facoltativi)",
    pdf_text: "Testo della bolletta", confirm: "Conferma e impara", cancel: "Annulla", saving: "Salvataggio…",
    missing: "Compila i quattro dati essenziali e il nome del fornitore.",
    learned_ok: "Confermata. Le prossime bollette di questo fornitore saranno lette in automatico.",
    learned_partial: (f) => `Confermata, ma non ho trovato nel testo: ${f}. Questi valori restano validi solo per questa bolletta.`,
    not_recognizable: "Il nome del fornitore non compare nel testo del PDF: controlla come è scritto, altrimenti la prossima bolletta non verrà riconosciuta.",
    setup_path: "Cartella delle bollette", setup_sources: "Sorgenti dei dati energia",
    setup_change: "Modifica configurazione", setup_templates: "Fornitori conosciuti",
    tpl_learned: "appreso dalle tue bollette", tpl_seed: "precaricato, da confermare con la prima bolletta",
    none: "nessuna",
    role_pv: "Produzione fotovoltaica", role_grid_import: "Prelievo dalla rete", role_grid_export: "Immissione in rete",
    role_consumption_add: "Consumo casa, somma di", role_consumption_subtract: "Consumo casa, meno",
    role_battery_charge: "Carica batteria", role_battery_discharge: "Scarica batteria",
    consumption_balance: "Consumo casa calcolato dal bilancio energetico",
    missing_sources: "Queste sorgenti non hanno statistiche nel periodo:",
    issue: {
      missing_field: "Valore mancante", period_reversed: "La data di fine precede quella di inizio",
      period_too_long: "Periodo troppo lungo: probabilmente le date sono sbagliate",
      negative_consumption: "Consumo negativo", bands_mismatch: "F1 + F2 + F3 non corrispondono al totale fatturato",
      parts_mismatch: "Le voci di costo non sommano al totale", implausible_unit_price: "Prezzo al kWh poco plausibile",
      no_text: "Il PDF non contiene testo leggibile", gas_bill: "Bolletta del gas: non entra nel confronto",
    },
    field: {
      period_start: "Inizio periodo", period_end: "Fine periodo", total_cost: "Totale da pagare (€)",
      consumption_kwh: "Consumo fatturato (kWh)", bill_number: "Numero bolletta", issue_date: "Data emissione",
      consumption_f1: "Consumo F1 (kWh)", consumption_f2: "Consumo F2 (kWh)", consumption_f3: "Consumo F3 (kWh)",
      cost_energy: "Materia energia (€)", cost_transport: "Trasporto e contatore (€)", cost_system: "Oneri di sistema (€)",
      cost_variable: "Costi variabili (€)", cost_fixed: "Costi fissi (€)", cost_recalc: "Ricalcoli (€)",
      cost_other: "Altre partite (€)", cost_bonus: "Bonus sociale (€)", cost_taxes: "Imposte e IVA (€)", cost_tv: "Canone TV (€)",
    },
  },
  en: {
    tab_overview: "Overview", tab_bills: "Bills", tab_setup: "Setup",
    hero: "Total saved with your plant",
    hero_estimated: (d) => `Estimated savings since ${d}`,
    hero_estimated_sub: "from your plant's data, at the price of the latest bill",
    no_overlap: (bills, plant) => `Your bills end on ${bills} and your plant's data starts on ${plant}: they share no days, so a bill by bill comparison is not possible yet. It will appear with the next bill.`,
    plant_produced: "Produced by the plant", plant_consumed: "Used by the plant's loads",
    plant_since: (d, n) => `since ${d}, ${n} days measured`,
    hero_sub: (n) => `across ${n} ${n === 1 ? "bill" : "bills"}`,
    paid: "Paid on bills", without: "Without the plant you would have paid",
    self_suff: "Self-sufficiency, latest bill",
    current: "Not billed yet", current_sub: (d) => `${d} ${d === 1 ? "day" : "days"} after the latest bill`,
    chart_cost: "What you paid and what you saved", chart_energy: "Where your energy came from",
    series_paid: "Paid", series_saved: "Saved", series_grid: "From the grid", series_plant: "From the plant",
    one_bill: "Charts appear from the second bill on.",
    table: "Bill by bill",
    th_period: "Period", th_supplier: "Supplier", th_billed: "From the grid", th_meter: "Grid measured",
    th_delta: "Difference", th_consumed: "Consumed", th_plant_loads: "From the plant", th_home: "Month total",
    th_price_unit: "€/kWh unit", series_total: "Total",
    legend_title: "How savings are calculated",
    legend_steps: [
      "Simulated bill: the bill's energy cost + the solar kWh from VRM at the supplier's price, as if the supplier had provided them.",
      "Unit cost: simulated bill ÷ all the kWh of the period (grid + solar).",
      "Savings: unit cost × solar kWh.",
    ],
    legend_notes: "Supplier's price: consumption charge with its taxes. TV licence and other items excluded. \"Without plant\" = real bill + solar kWh at that price: fixed charges do not change, so its difference from what you paid is lower than the savings.",
    legend_example: (p, cost, kwh, price, grid, unit, saved) => `Example, ${p}: (€${cost} + ${kwh} kWh × €${price}) ÷ (${grid} + ${kwh}) kWh = €${unit}/kWh; × ${kwh} kWh = €${saved} saved.`,
    legend_variable: "Savings = solar kWh × consumption charge with its taxes. Fixed charges stay out, because they are due anyway.",
    legend_manual: "A manual price is set: savings = solar kWh × that price.",
    setup_layout: "Grid connection",
    setup_vrm: "VRM portal, installation", setup_vrm_download: "Latest download",
    vrm_auth_error: "VRM refused the access token: new plant data is not being downloaded. Update the token in the integration options.",
    vrm_unreachable: "VRM cannot be reached right now: the figures use data already downloaded, and it will try again at the next update.",
    layout_through_plant: "The grid feeds the plant, and the plant feeds the home.",
    layout_separate: "Separate: the plant runs its own loads as an island, the bill pays for the other circuits.", th_pv: "Produced", th_self: "Self-suff.",
    th_paid: "Paid", th_without: "Without plant", th_saved: "Saved", th_price: "€/kWh",
    no_measure: "no data", partial: (p) => `data for ${p}% of the period`,
    superseded: "replaced by a newer bill", overlapping: "period overlaps another bill",
    review_banner: (n) => `${n} ${n === 1 ? "bill is" : "bills are"} waiting for your confirmation`,
    review_open: "Review",
    empty_title: "Upload your first bill",
    empty_text: "Drop a PDF here or copy it into the bills folder. The first bill from each supplier needs your confirmation: after that, reading is automatic.",
    price_warn: "On some bills the price per kWh is an average that includes fixed charges, so savings are overstated. Set a price in Setup to correct it.",
    upload: "Upload PDF", uploading: "Uploading…", rescan: "Check the folder",
    drop: "Drop PDF bills here", duplicate: "This bill is already here.",
    upload_failed: "Upload failed", admin_only: "Only an administrator can upload and confirm bills.",
    th_file: "File", th_status: "Status", th_total: "Total", review: "Review", edit: "Correct",
    status_ok: "Read", status_needs_review: "To confirm", status_needs_learning: "New supplier",
    status_unreadable: "To fill in", status_ignored: "Gas, ignored",
    review_title: "Check the values read",
    review_help: "Fix anything wrong by looking at the text on the right. When you confirm, OffGrid2Save learns where these values are and reads the next bills from this supplier on its own.",
    review_unreadable: "This PDF has no text (a scan or a protected file). You can type the values: they apply to this bill only.",
    supplier: "Supplier name, as printed on the bill",
    group_main: "Essential data", group_costs: "Cost items (optional)", group_more: "More data (optional)",
    pdf_text: "Bill text", confirm: "Confirm and learn", cancel: "Cancel", saving: "Saving…",
    missing: "Fill in the four essential values and the supplier name.",
    learned_ok: "Confirmed. The next bills from this supplier will be read automatically.",
    learned_partial: (f) => `Confirmed, but not found in the text: ${f}. These values apply to this bill only.`,
    not_recognizable: "The supplier name does not appear in the PDF text: check its spelling, or the next bill will not be recognized.",
    setup_path: "Bills folder", setup_sources: "Energy data sources",
    setup_change: "Change configuration", setup_templates: "Known suppliers",
    tpl_learned: "learned from your bills", tpl_seed: "built in, confirm it with the first bill",
    none: "none",
    role_pv: "Solar production", role_grid_import: "Grid import", role_grid_export: "Grid export",
    role_consumption_add: "Home consumption, sum of", role_consumption_subtract: "Home consumption, minus",
    role_battery_charge: "Battery charge", role_battery_discharge: "Battery discharge",
    consumption_balance: "Home consumption derived from the energy balance",
    missing_sources: "These sources have no statistics in the period:",
    issue: {
      missing_field: "Missing value", period_reversed: "The end date is before the start date",
      period_too_long: "Period too long: the dates are probably wrong",
      negative_consumption: "Negative consumption", bands_mismatch: "F1 + F2 + F3 do not match the billed total",
      parts_mismatch: "Cost items do not add up to the total", implausible_unit_price: "Unlikely price per kWh",
      no_text: "The PDF has no readable text", gas_bill: "Gas bill: left out of the comparison",
    },
    field: {
      period_start: "Period start", period_end: "Period end", total_cost: "Total to pay (€)",
      consumption_kwh: "Billed consumption (kWh)", bill_number: "Bill number", issue_date: "Issue date",
      consumption_f1: "F1 consumption (kWh)", consumption_f2: "F2 consumption (kWh)", consumption_f3: "F3 consumption (kWh)",
      cost_energy: "Energy (€)", cost_transport: "Transport and meter (€)", cost_system: "System charges (€)",
      cost_variable: "Variable costs (€)", cost_fixed: "Fixed costs (€)", cost_recalc: "Recalculations (€)",
      cost_other: "Other items (€)", cost_bonus: "Social bonus (€)", cost_taxes: "Taxes and VAT (€)", cost_tv: "TV licence (€)",
    },
  },
};

const STATUS_GLYPH = {
  ok: ["✓", "good"], needs_review: ["!", "warning"], needs_learning: ["?", "warning"],
  unreadable: ["×", "critical"], ignored: ["–", "muted"],
};

const esc = (value) =>
  String(value ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]);

const STYLE = `
:host { display:block; height:100%; overflow:auto; background:var(--primary-background-color);
  color:var(--primary-text-color); font-family:var(--paper-font-body1_-_font-family, system-ui, sans-serif);
  --series-1:#2a78d6; --series-2:#eb6834; --grid:#e1e0d9; --axis:#c3c2b7; --ink-2:#52514e; --muted:#6f6e69;
  --good:#006300; --warning:#8a5a00; --critical:#d03b3b; --surface:var(--card-background-color,#fff); }
:host([dark]) { --series-1:#3987e5; --series-2:#d95926; --grid:#2c2c2a; --axis:#383835; --ink-2:#c3c2b7; --muted:#a3a29a;
  --good:#0ca30c; --warning:#fab219; --critical:#e66767; }
* { box-sizing:border-box; }
header { display:flex; align-items:center; gap:8px; height:56px; padding:0 16px; background:var(--app-header-background-color,var(--primary-color));
  color:var(--app-header-text-color,#fff); position:sticky; top:0; z-index:2; }
header h1 { font-size:20px; font-weight:400; margin:0; flex:1; }
nav { display:flex; gap:4px; }
nav button { background:none; border:0; color:inherit; font:inherit; padding:8px 12px; border-radius:6px; cursor:pointer; opacity:.8; }
nav button[aria-current="page"] { opacity:1; background:rgba(255,255,255,.18); font-weight:500; }
main { max-width:1180px; margin:0 auto; padding:16px; display:grid; gap:16px; }
.card { background:var(--surface); border-radius:var(--ha-card-border-radius,12px); padding:16px;
  border:1px solid var(--divider-color,rgba(0,0,0,.12)); min-width:0; }
.card h2 { font-size:16px; font-weight:500; margin:0 0 12px; }
.hero { font-size:52px; font-weight:600; line-height:1.1; }
.sub { color:var(--ink-2); font-size:14px; margin-top:4px; }
.tiles { display:grid; gap:16px; grid-template-columns:repeat(auto-fit,minmax(200px,1fr)); }
.tile .label { color:var(--ink-2); font-size:14px; }
.tile .value { font-size:26px; font-weight:600; margin-top:6px; }
.charts { display:grid; gap:16px; grid-template-columns:repeat(auto-fit,minmax(340px,1fr)); }
.legend { display:flex; gap:16px; font-size:13px; color:var(--ink-2); margin-bottom:8px; }
.swatch { display:inline-block; width:10px; height:10px; border-radius:3px; margin-right:6px; }
.chart { position:relative; }
.chart svg { display:block; width:100%; }
.chart text { fill:var(--muted); font-size:12px; font-variant-numeric:tabular-nums; }
.chart text.tip-label { fill:var(--primary-text-color); font-weight:500; }
.hit { fill:transparent; outline:none; cursor:default; }
.hit:hover, .hit:focus { fill:var(--secondary-background-color,rgba(127,127,127,.12)); fill-opacity:.5; }
.tooltip { position:absolute; pointer-events:none; background:var(--surface); border:1px solid var(--divider-color,#ccc); border-radius:8px;
  padding:8px 10px; font-size:13px; box-shadow:0 2px 8px rgba(0,0,0,.18); white-space:nowrap; z-index:1; }
.tooltip b { display:block; margin-bottom:4px; font-weight:500; }
.tooltip div { display:flex; justify-content:space-between; gap:16px; }
.scroll { overflow-x:auto; }
table { border-collapse:collapse; width:100%; font-size:14px; }
th { text-align:left; font-weight:500; color:var(--ink-2); font-size:13px; }
th, td { padding:8px 10px; border-bottom:1px solid var(--divider-color,rgba(0,0,0,.12)); vertical-align:top; white-space:nowrap; }
td.num, th.num { text-align:right; font-variant-numeric:tabular-nums; }
.note { display:block; font-size:12px; color:var(--ink-2); white-space:normal; min-width:130px; }
.status { display:inline-flex; align-items:center; gap:6px; font-size:14px; }
.glyph { display:inline-flex; width:18px; height:18px; border-radius:50%; align-items:center; justify-content:center;
  font-size:12px; font-weight:700; color:#fff; }
.glyph.good { background:#0ca30c; } .glyph.warning { background:#fab219; color:#0b0b0b; }
.glyph.critical { background:#d03b3b; } .glyph.muted { background:#898781; }
.banner { display:flex; align-items:center; gap:12px; justify-content:space-between; flex-wrap:wrap; }
.banner.warn { border-left:4px solid #fab219; }
button.action { background:var(--primary-color); color:var(--text-primary-color,#fff); border:0; border-radius:6px; padding:8px 14px; font:inherit; cursor:pointer; }
button.ghost { background:none; color:var(--primary-color); border:1px solid var(--divider-color,#ccc); border-radius:6px; padding:8px 14px; font:inherit; cursor:pointer; }
button[disabled] { opacity:.6; cursor:default; }
.drop { border:2px dashed var(--divider-color,#bbb); border-radius:12px; padding:24px; text-align:center; color:var(--ink-2); }
.drop.over { border-color:var(--primary-color); color:var(--primary-text-color); }
.drop .row { display:flex; gap:8px; justify-content:center; margin-top:12px; flex-wrap:wrap; }
.review { display:grid; gap:16px; grid-template-columns:minmax(300px,420px) minmax(0,1fr); align-items:start; }
.narrow header { padding:0 4px; }
.narrow header h1 { display:none; }
.narrow nav { margin-left:auto; gap:0; }
.narrow nav button { padding:8px; font-size:14px; }
.text-card { position:sticky; top:72px; }
.narrow .review { grid-template-columns:minmax(0,1fr); }
.narrow .text-card { position:static; }
label.field { display:block; margin-bottom:10px; font-size:13px; color:var(--ink-2); }
label.field input { display:block; width:100%; margin-top:4px; padding:8px; font:inherit; color:var(--primary-text-color);
  background:var(--secondary-background-color,transparent); border:1px solid var(--divider-color,#bbb); border-radius:6px; color-scheme:inherit; }
label.field input:focus { outline:2px solid var(--primary-color); outline-offset:-1px; }
details { margin-bottom:12px; } summary { cursor:pointer; font-weight:500; margin-bottom:10px; }
.text { font-family:ui-monospace,Consolas,monospace; font-size:12px; line-height:1.5; max-height:70vh; overflow:auto;
  white-space:pre; background:var(--secondary-background-color,transparent); border-radius:6px; padding:8px; }
.text .line.hit-line { background:rgba(250,178,25,.35); outline:1px solid #fab219; }
.issues { margin:0 0 12px; padding:0; list-style:none; font-size:14px; }
.issues li { display:flex; gap:8px; align-items:center; margin-bottom:4px; }
.msg { padding:10px 12px; border-radius:8px; background:var(--secondary-background-color,rgba(127,127,127,.12)); font-size:14px; }
.buttons { display:flex; gap:8px; margin-top:8px; }
ol.steps { margin:0 0 8px; padding-left:20px; font-size:14px; line-height:1.5; }
.entity { font-family:ui-monospace,Consolas,monospace; font-size:12px; display:block; color:var(--ink-2); white-space:normal; word-break:break-all; }
dl { display:grid; grid-template-columns:minmax(150px,240px) minmax(0,1fr); gap:10px 16px; margin:0; font-size:14px; }
dt { color:var(--ink-2); } dd { margin:0; }
.narrow dl { grid-template-columns:minmax(0,1fr); }
`;

class OffGrid2SavePanel extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    this._view = "overview";
    this._data = null;
    this._review = null;
    this._message = null;
    this._busy = false;
    this._chartWidth = 0;
  }

  set hass(hass) {
    const firstTime = !this._hass;
    this._hass = hass;
    this.toggleAttribute("dark", Boolean(hass.themes && hass.themes.darkMode));
    if (firstTime) this._load();
    const menu = this.shadowRoot.querySelector("ha-menu-button");
    if (menu) menu.hass = hass;
  }

  set narrow(value) {
    if (this._narrow === value) return;
    this._narrow = value;
    this._render();
  }

  connectedCallback() {
    this._poll = setInterval(() => { if (!this._review) this._load(); }, POLL_MS);
    this._resize = new ResizeObserver(() => {
      const width = this.shadowRoot.querySelector(".chart")?.clientWidth || 0;
      if (width && Math.abs(width - this._chartWidth) > 8) { this._chartWidth = width; this._render(); }
    });
    this._resize.observe(this);
    this.shadowRoot.addEventListener("click", (e) => this._onClick(e));
    this.shadowRoot.addEventListener("focusin", (e) => this._onFocus(e));
    this.shadowRoot.addEventListener("focusout", () => this._hideTip());
    this.shadowRoot.addEventListener("mouseover", (e) => this._onFocus(e));
    this.shadowRoot.addEventListener("mouseout", (e) => { if (e.target.classList?.contains("hit")) this._hideTip(); });
    this.shadowRoot.addEventListener("change", (e) => this._onChange(e));
    for (const type of ["dragover", "dragleave", "drop"]) this.addEventListener(type, (e) => this._onDrag(e));
  }

  disconnectedCallback() {
    clearInterval(this._poll);
    this._resize?.disconnect();
  }

  get _t() {
    const lang = (this._hass?.language || "en").slice(0, 2);
    return STRINGS[lang] || STRINGS.en;
  }

  get _isAdmin() { return Boolean(this._hass?.user?.is_admin); }

  _num(value, digits = 0) {
    if (value === null || value === undefined) return "–";
    return new Intl.NumberFormat(this._hass?.language || "it", { minimumFractionDigits: digits, maximumFractionDigits: digits }).format(value);
  }

  _eur(value) { return value === null || value === undefined ? "–" : `${this._num(value, 2)} €`; }

  _date(iso) {
    if (!iso) return "–";
    const [y, m, d] = iso.split("-").map(Number);
    return new Date(y, m - 1, d).toLocaleDateString(this._hass?.language || "it", { day: "2-digit", month: "2-digit", year: "2-digit" });
  }

  _shortPeriod(values) {
    const fmt = (iso) => {
      const [y, m] = iso.split("-").map(Number);
      return new Date(y, m - 1, 1).toLocaleDateString(this._hass?.language || "it", { month: "short" });
    };
    const start = fmt(values.period_start), end = fmt(values.period_end);
    const year = values.period_end.slice(2, 4);
    return start === end ? `${start} ${year}` : `${start}–${end} ${year}`;
  }

  async _load() {
    if (!this._hass) return;
    try {
      this._data = await this._hass.callWS({ type: "offgrid2save/overview" });
    } catch (err) {
      this._error = err.message || String(err);
    }
    this._render();
  }

  // ---------------------------------------------------------------- rendering

  _render() {
    if (!this._hass) return;
    const t = this._t;
    const scrollTop = this.shadowRoot.querySelector(".text")?.scrollTop;
    let body = "";
    if (this._review) body = this._reviewHtml();
    else if (!this._data) body = this._error ? `<div class="card">${esc(this._error)}</div>` : "";
    else if (this._view === "bills") body = this._billsHtml();
    else if (this._view === "setup") body = this._setupHtml();
    else body = this._overviewHtml();

    const tab = (id, label) =>
      `<button data-action="view" data-view="${id}" ${this._view === id && !this._review ? 'aria-current="page"' : ""}>${esc(label)}</button>`;
    this.shadowRoot.innerHTML = `<style>${STYLE}</style>
      <div class="${this._narrow ? "narrow" : ""}">
        <header>
          <span id="menu"></span>
          <h1>OffGrid2Save</h1>
          <nav>${tab("overview", t.tab_overview)}${tab("bills", t.tab_bills)}${tab("setup", t.tab_setup)}</nav>
        </header>
        <main>${this._message ? `<div class="card msg" role="status">${esc(this._message)}</div>` : ""}${body}</main>
        <input type="file" id="file" accept="application/pdf,.pdf" multiple hidden>
      </div>`;

    if (this._narrow && customElements.get("ha-menu-button")) {
      const menu = document.createElement("ha-menu-button");
      menu.hass = this._hass;
      menu.narrow = true;
      this.shadowRoot.getElementById("menu").append(menu);
    }
    if (scrollTop) {
      const text = this.shadowRoot.querySelector(".text");
      if (text) text.scrollTop = scrollTop;
    }
    if (!this._chartWidth) {
      const width = this.shadowRoot.querySelector(".chart")?.clientWidth;
      if (width) { this._chartWidth = width; this._render(); }
    }
  }

  _countedBills() {
    return this._data.bills.filter((b) => b.status === "ok" && !b.superseded && b.comparison);
  }

  _overviewHtml() {
    const t = this._t, data = this._data;
    if (!data.bills.length) return `${this._dropHtml(true)}${this._plantTiles()}`;

    const counted = this._countedBills();
    const measured = counted.filter((b) => b.comparison.savings_eur !== null);
    const last = measured[measured.length - 1];
    const current = data.current_period;
    const banner = data.to_review
      ? `<div class="card banner warn"><span>${esc(t.review_banner(data.to_review))}</span>
         <button class="action" data-action="view" data-view="bills">${esc(t.review_open)}</button></div>`
      : "";
    const priceWarn = measured.some((b) => b.comparison.enel_price_source === "all_in_average")
      ? `<div class="card banner warn">${esc(t.price_warn)}</div>` : "";

    let tiles = "";
    if (measured.length) {
      tiles = `<div class="tiles">
        ${this._tile(t.paid, this._eur(data.totals.cost_eur))}
        ${this._tile(t.without, this._eur(data.totals.cost_without_plant_eur))}
        ${last ? this._tile(t.self_suff, last.comparison.self_sufficiency_pct === null ? "–" : `${this._num(last.comparison.self_sufficiency_pct)}%`) : ""}
        ${current && current.savings_eur !== null ? this._tile(t.current, this._eur(current.savings_eur), t.current_sub(current.energy.covered_days)) : ""}
      </div>`;
    }
    const plant = data.plant;
    let notice = "";
    let hero = `<div class="card"><div class="tile"><div class="label">${esc(t.hero)}</div>
        <div class="hero">${esc(this._eur(data.totals.savings_eur))}</div>
        <div class="sub">${esc(t.hero_sub(measured.length))}</div></div></div>`;
    if (!measured.length && plant) {
      // Showing 0 here would say the plant saved nothing, when the two simply never met.
      const lastBill = counted.map((b) => b.values.period_end).sort().pop();
      if (lastBill) notice = `<div class="card banner warn">${esc(t.no_overlap(this._date(lastBill), this._date(plant.energy.start)))}</div>`;
      if (plant.savings_eur !== null) {
        hero = `<div class="card"><div class="tile"><div class="label">${esc(t.hero_estimated(this._date(plant.energy.start)))}</div>
          <div class="hero">${esc(this._eur(plant.savings_eur))}</div>
          <div class="sub">${esc(t.hero_estimated_sub)}</div></div></div>`;
      }
    }

    const charts = measured.length >= 2
      ? `<div class="charts">
          <div class="card"><h2>${esc(t.chart_cost)}</h2>${this._stackChart(measured, "cost")}</div>
          <div class="card"><h2>${esc(t.chart_energy)}</h2>${this._stackChart(measured, "energy")}</div>
        </div>`
      : measured.length === 1 ? `<div class="sub">${esc(t.one_bill)}</div>` : "";

    const vrmIssue = data.vrm && data.vrm.status !== "ok"
      ? `<div class="card banner warn">${esc(data.vrm.status === "auth_error" ? t.vrm_auth_error : t.vrm_unreachable)}</div>` : "";
    return `${banner}${vrmIssue}${hero}${notice}
      ${priceWarn}${tiles}${this._plantTiles()}${charts}${counted.length ? this._comparisonTable(counted) : ""}`;
  }

  _plantTiles() {
    const t = this._t, plant = this._data.plant;
    if (!plant) return "";
    const since = t.plant_since(this._date(plant.energy.start), plant.energy.covered_days);
    return `<div class="tiles">
      ${this._tile(t.plant_produced, `${this._num(plant.energy.pv_kwh)} kWh`, since)}
      ${this._tile(t.plant_consumed, `${this._num(plant.energy.consumption_kwh)} kWh`, since)}
    </div>`;
  }

  _tile(label, value, sub) {
    return `<div class="card tile"><div class="label">${esc(label)}</div><div class="value">${esc(value)}</div>${sub ? `<div class="sub">${esc(sub)}</div>` : ""}</div>`;
  }

  _chartRows(bills, kind) {
    const t = this._t;
    return bills.map((bill) => {
      const c = bill.comparison;
      const label = this._shortPeriod(bill.values);
      if (kind === "cost") {
        const paid = bill.values.total_cost;
        const saved = Math.max(c.savings_eur, 0);
        return { label, parts: [Math.max(paid, 0), saved], total: paid + saved,
          tip: [[t.series_paid, this._eur(paid)], [t.series_saved, this._eur(c.savings_eur)]] };
      }
      const plant = c.avoided_kwh || 0;
      const grid = Math.max(c.grid_kwh || 0, 0);
      return { label, parts: [grid, plant], total: grid + plant,
        tip: [[t.series_grid, `${this._num(grid)} kWh`], [t.series_plant, `${this._num(plant)} kWh`], [t.series_total, `${this._num(grid + plant)} kWh`]] };
    });
  }

  _stackChart(bills, kind) {
    const t = this._t;
    const rows = this._chartRows(bills, kind);
    const names = kind === "cost" ? [t.series_paid, t.series_saved] : [t.series_grid, t.series_plant];
    const unit = kind === "cost" ? "€" : "kWh";
    const width = this._chartWidth || 480;
    const left = 44, right = 8, top = 22, plot = 200, bottom = 26;
    const inner = width - left - right;
    const band = inner / rows.length;
    const thick = Math.min(24, band * 0.55);
    const max = Math.max(...rows.map((r) => r.total), 1);
    const step = this._niceStep(max / 4);
    const yMax = Math.ceil(max / step) * step;
    const y = (value) => top + plot - (value / yMax) * plot;

    let svg = "";
    for (let tick = 0; tick <= yMax + step / 2; tick += step) {
      svg += `<line x1="${left}" x2="${width - right}" y1="${y(tick)}" y2="${y(tick)}" stroke="var(${tick === 0 ? "--axis" : "--grid"})" stroke-width="1"/>
        <text x="${left - 6}" y="${y(tick) + 4}" text-anchor="end">${esc(this._num(tick))}</text>`;
    }
    const labelEvery = Math.max(1, Math.ceil(70 / band));
    rows.forEach((row, index) => {
      const x = left + band * index + (band - thick) / 2;
      const [lower, upper] = row.parts;
      const lowerTop = y(lower), upperTop = y(lower + upper);
      const gap = lower > 0 && upper > 0 ? 2 : 0;
      if (lower > 0) svg += `<path fill="var(--series-1)" d="${this._barPath(x, lowerTop + (upper > 0 ? gap : 0), thick, y(0), upper <= 0)}"/>`;
      if (upper > 0) svg += `<path fill="var(--series-2)" d="${this._barPath(x, upperTop, thick, lowerTop, true)}"/>`;
      // Paid plus saved is not an amount anyone pays: only the energy total deserves a label.
      if (index === rows.length - 1 && kind !== "cost") {
        svg += `<text class="tip-label" x="${x + thick / 2}" y="${upperTop - 6}" text-anchor="middle">${esc(this._num(row.total))} ${esc(unit)}</text>`;
      }
      if (index % labelEvery === 0 || index === rows.length - 1) {
        svg += `<text x="${x + thick / 2}" y="${top + plot + 18}" text-anchor="middle">${esc(row.label)}</text>`;
      }
      const description = `${row.label}: ${row.tip.map(([n, v]) => `${n} ${v}`).join(", ")}`;
      svg += `<rect class="hit" tabindex="0" role="img" aria-label="${esc(description)}" x="${left + band * index}" y="${top}" width="${band}" height="${plot}"
        data-tip="${esc(JSON.stringify({ label: row.label, tip: row.tip }))}"></rect>`;
    });
    const legend = names.map((name, i) => `<span><span class="swatch" style="background:var(--series-${i + 1})"></span>${esc(name)}</span>`).join("");
    return `<div class="legend">${legend}</div><div class="chart">
      <svg height="${top + plot + bottom}" viewBox="0 0 ${width} ${top + plot + bottom}">${svg}</svg></div>`;
  }

  _barPath(x, topY, width, baseY, roundTop) {
    const height = Math.max(baseY - topY, 0);
    const radius = roundTop ? Math.min(4, height, width / 2) : 0;
    return `M${x},${baseY}V${topY + radius}Q${x},${topY} ${x + radius},${topY}H${x + width - radius}Q${x + width},${topY} ${x + width},${topY + radius}V${baseY}Z`;
  }

  _niceStep(raw) {
    const power = 10 ** Math.floor(Math.log10(raw || 1));
    const scaled = raw / power;
    return (scaled <= 1 ? 1 : scaled <= 2 ? 2 : scaled <= 5 ? 5 : 10) * power;
  }

  _comparisonTable(bills) {
    const t = this._t;
    // With a separate plant the bill and the plant's counters measure different
    // circuits: a "grid measured" column and a difference would mean nothing.
    const throughPlant = this._data.layout !== "separate";
    const rows = [...bills].reverse().map((bill) => {
      const c = bill.comparison, e = c.energy;
      const notes = [];
      if (bill.superseded) notes.push(t.superseded);
      if (bill.overlapping) notes.push(t.overlapping);
      if (c.partial && c.coverage_pct > 0) notes.push(t.partial(this._num(c.coverage_pct)));
      if (c.coverage_pct === 0) notes.push(t.no_measure);
      const delta = c.meter_delta_pct;
      const deltaWarn = delta !== null && Math.abs(delta) > METER_DELTA_WARN_PCT
        && Math.abs(c.meter_delta_kwh) >= METER_DELTA_WARN_KWH;
      const measured = c.coverage_pct > 0;
      return `<tr>
        <td>${esc(this._date(bill.values.period_start))} – ${esc(this._date(bill.values.period_end))}
          ${notes.length ? `<span class="note">${esc(notes.join(" · "))}</span>` : ""}</td>
        <td>${esc(bill.supplier || "–")}</td>
        <td class="num">${esc(this._num(bill.values.consumption_kwh))}</td>
        ${throughPlant ? `<td class="num">${measured ? esc(this._num(e.grid_import_kwh)) : "–"}</td>
        <td class="num">${c.meter_delta_kwh === null ? "–" : `${deltaWarn ? '<span class="glyph warning" title="">!</span> ' : ""}${esc(this._num(c.meter_delta_kwh))}`}</td>` : ""}
        <td class="num">${measured ? esc(this._num(e.consumption_kwh)) : "–"}</td>
        ${throughPlant ? "" : `<td class="num">${c.home_kwh === null ? "–" : esc(this._num(c.home_kwh))}</td>`}
        <td class="num">${measured ? esc(this._num(e.pv_kwh)) : "–"}</td>
        <td class="num">${c.self_sufficiency_pct === null ? "–" : `${esc(this._num(c.self_sufficiency_pct))}%`}</td>
        <td class="num">${esc(this._eur(bill.values.total_cost))}</td>
        <td class="num">${esc(this._eur(c.cost_without_plant_eur))}</td>
        <td class="num">${esc(this._eur(c.savings_eur))}</td>
        <td class="num">${c.price_eur_kwh === null ? "–" : esc(this._num(c.price_eur_kwh, 3))}</td>
      </tr>`;
    }).join("");
    return `<div class="card"><h2>${esc(t.table)}</h2><div class="scroll"><table>
      <thead><tr><th>${esc(t.th_period)}</th><th>${esc(t.th_supplier)}</th>
      <th class="num">${esc(t.th_billed)} kWh</th>${throughPlant ? `<th class="num">${esc(t.th_meter)} kWh</th><th class="num">${esc(t.th_delta)} kWh</th>` : ""}
      <th class="num">${esc(throughPlant ? t.th_consumed : t.th_plant_loads)} kWh</th>${throughPlant ? "" : `<th class="num">${esc(t.th_home)} kWh</th>`}<th class="num">${esc(t.th_pv)} kWh</th><th class="num">${esc(t.th_self)}</th>
      <th class="num">${esc(t.th_paid)}</th><th class="num">${esc(t.th_without)}</th><th class="num">${esc(t.th_saved)}</th><th class="num">${esc(this._data.price_method === "whole_home" ? t.th_price_unit : t.th_price)}</th></tr></thead>
      <tbody>${rows}</tbody></table></div></div>`;
  }

  _dropHtml(empty) {
    const t = this._t;
    if (!this._isAdmin) return `<div class="card">${esc(t.admin_only)}</div>`;
    return `<div class="drop ${this._dragging ? "over" : ""}">
      ${empty ? `<h2>${esc(t.empty_title)}</h2><div>${esc(t.empty_text)}</div>` : esc(t.drop)}
      <div class="row"><button class="action" data-action="pick" ${this._busy ? "disabled" : ""}>${esc(this._busy ? t.uploading : t.upload)}</button>
      <button class="ghost" data-action="rescan" ${this._busy ? "disabled" : ""}>${esc(t.rescan)}</button></div></div>`;
  }

  _statusHtml(status) {
    const [glyph, tone] = STATUS_GLYPH[status] || ["?", "muted"];
    return `<span class="status"><span class="glyph ${tone}" aria-hidden="true">${glyph}</span>${esc(this._t[`status_${status}`] || status)}</span>`;
  }

  _billsHtml() {
    const t = this._t;
    const rows = [...this._data.bills].reverse().map((bill) => {
      const needsAction = ["needs_review", "needs_learning", "unreadable"].includes(bill.status);
      const canOpen = this._isAdmin && bill.status !== "ignored";
      const issues = bill.issues.filter((i) => i.level === "warning").map((i) => t.issue[i.code] || i.code);
      return `<tr>
        <td style="white-space:normal">${esc(bill.file)}${issues.length ? `<span class="note">${esc(issues.join(" · "))}</span>` : ""}</td>
        <td>${this._statusHtml(bill.status)}</td>
        <td>${esc(bill.supplier || "–")}</td>
        <td>${bill.values.period_start ? `${esc(this._date(bill.values.period_start))} – ${esc(this._date(bill.values.period_end))}` : "–"}</td>
        <td class="num">${esc(this._eur(bill.values.total_cost))}</td>
        <td>${canOpen ? `<button class="${needsAction ? "action" : "ghost"}" data-action="review" data-id="${esc(bill.id)}">${esc(needsAction ? t.review : t.edit)}</button>` : ""}</td>
      </tr>`;
    }).join("");
    return `${this._dropHtml(!this._data.bills.length)}
      ${rows ? `<div class="card"><div class="scroll"><table><thead><tr>
        <th>${esc(t.th_file)}</th><th>${esc(t.th_status)}</th><th>${esc(t.th_supplier)}</th><th>${esc(t.th_period)}</th>
        <th class="num">${esc(t.th_total)}</th><th></th></tr></thead><tbody>${rows}</tbody></table></div></div>` : ""}`;
  }

  _setupHtml() {
    const t = this._t, data = this._data;
    const roles = data.vrm
      ? `<dt>${esc(t.setup_vrm)}</dt><dd>${esc(data.vrm.site || "–")}</dd>
         <dt>${esc(t.setup_vrm_download)}</dt><dd>${esc(data.vrm.last_download ? new Date(data.vrm.last_download).toLocaleString(this._hass.language) : "–")}</dd>`
      : Object.entries(data.sources).map(([role, ids]) => {
      if (!ids.length) return `<dt>${esc(t[`role_${role}`] || role)}</dt><dd>${esc(t.none)}</dd>`;
      return `<dt>${esc(t[`role_${role}`] || role)}</dt><dd>${ids.map((id) => `<span class="entity">${esc(id)}</span>`).join("")}</dd>`;
    }).join("");
    const missing = new Set();
    let balance = false;
    for (const bill of data.bills) {
      if (!data.vrm) for (const id of bill.comparison?.energy?.missing_sources || []) missing.add(id);
      if (bill.comparison?.energy?.consumption_method === "balance") balance = true;
    }
    const templates = data.templates.map((tpl) =>
      `<dt>${esc(tpl.name || tpl.id)}</dt><dd>${esc(tpl.learned ? t.tpl_learned : t.tpl_seed)}</dd>`).join("");
    return `<div class="card"><h2>${esc(t.setup_path)}</h2><span class="entity">${esc(data.bills_path)}</span></div>
      <div class="card"><h2>${esc(t.setup_layout)}</h2>${esc(t[`layout_${data.layout}`] || data.layout)}</div>
      <div class="card"><h2>${esc(t.setup_sources)}</h2><dl>${roles}</dl>
        ${balance ? `<p class="sub">${esc(t.consumption_balance)}</p>` : ""}
        ${missing.size ? `<p class="sub">${esc(t.missing_sources)}</p>${[...missing].map((id) => `<span class="entity">${esc(id)}</span>`).join("")}` : ""}
        ${this._isAdmin ? `<div class="buttons"><a href="/config/integrations/integration/offgrid2save"><button class="ghost">${esc(t.setup_change)}</button></a></div>` : ""}
      </div>
      <div class="card"><h2>${esc(t.setup_templates)}</h2><dl>${templates}</dl></div>
      ${this._legendHtml()}`;
  }

  _legendHtml() {
    const t = this._t, data = this._data;
    const counted = this._countedBills().filter((b) => b.comparison.savings_eur !== null);
    if (counted.some((b) => b.comparison.price_source === "manual")) {
      return `<div class="card"><h2>${esc(t.legend_title)}</h2><p class="sub">${esc(t.legend_manual)}</p></div>`;
    }
    if (data.price_method !== "whole_home") {
      return `<div class="card"><h2>${esc(t.legend_title)}</h2><p class="sub">${esc(t.legend_variable)}</p></div>`;
    }
    const latest = [...counted].reverse().find((b) => b.comparison.simulated_bill_eur !== null && !b.comparison.partial);
    let example = "";
    if (latest) {
      const c = latest.comparison;
      const kwh = this._num(c.avoided_kwh, 1);
      example = `<p class="sub">${esc(t.legend_example(this._shortPeriod(latest.values), this._num(c.bill_energy_eur, 2), kwh, this._num(c.enel_price_eur_kwh, 3), this._num(latest.values.consumption_kwh, 1), this._num(c.price_eur_kwh, 3), this._num(c.savings_eur, 2)))}</p>`;
    }
    return `<div class="card"><h2>${esc(t.legend_title)}</h2>
      <ol class="steps">${t.legend_steps.map((step) => `<li>${esc(step)}</li>`).join("")}</ol>
      ${example}<p class="sub">${esc(t.legend_notes)}</p></div>`;
  }

  _reviewHtml() {
    const t = this._t, r = this._review;
    const blocking = r.bill.issues.map((i) =>
      `<li><span class="glyph ${i.level === "error" ? "critical" : "warning"}" aria-hidden="true">!</span>
       ${esc(t.issue[i.code] || i.code)}${i.field ? `: ${esc(t.field[i.field] || i.field)}` : ""}</li>`).join("");
    const groups = FIELD_GROUPS.map((group) => {
      const inputs = group.fields.map(([key, kind]) => {
        const type = kind === "date" ? "date" : kind === "text" ? "text" : "number";
        const step = kind === "eur" ? ' step="0.01"' : kind === "kwh" ? ' step="0.1"' : "";
        const value = r.values[key] ?? "";
        const line = r.bill.lines?.[key];
        return `<label class="field">${esc(t.field[key])}${REQUIRED.includes(key) ? " *" : ""}
          <input data-field="${key}" type="${type}"${step} value="${esc(value)}" ${line !== undefined ? `data-line="${line}"` : ""}></label>`;
      }).join("");
      const hasValue = group.fields.some(([key]) => r.values[key] !== undefined && r.values[key] !== null);
      return `<details ${group.open || hasValue ? "open" : ""}><summary>${esc(t[`group_${group.key}`])}</summary>${inputs}</details>`;
    }).join("");
    const lines = r.bill.text_lines || [];
    const textCard = lines.length
      // Runs of spaces come from the PDF columns and push values out of sight.
      ? `<div class="card text-card"><h2>${esc(t.pdf_text)}</h2><div class="text">${lines.map((line, i) =>
          `<div class="line ${r.activeLine === i ? "hit-line" : ""}" data-index="${i}">${esc(line.trim().replace(/ {3,}/g, "   ")) || " "}</div>`).join("")}</div></div>`
      : `<div class="card msg">${esc(t.review_unreadable)}</div>`;
    return `<div class="review">
      <div class="card"><h2>${esc(t.review_title)}</h2>
        <p class="sub">${esc(t.review_help)}</p>
        <p class="sub"><b>${esc(r.bill.file)}</b></p>
        ${blocking ? `<ul class="issues">${blocking}</ul>` : ""}
        <label class="field">${esc(t.supplier)} *<input data-supplier value="${esc(r.supplier)}"></label>
        ${groups}
        ${r.error ? `<div class="msg" role="alert">${esc(r.error)}</div>` : ""}
        <div class="buttons"><button class="action" data-action="confirm" ${this._busy ? "disabled" : ""}>${esc(this._busy ? t.saving : t.confirm)}</button>
        <button class="ghost" data-action="cancel">${esc(t.cancel)}</button></div>
      </div>${textCard}</div>`;
  }

  // ------------------------------------------------------------------- events

  _onClick(event) {
    const button = event.target.closest("[data-action]");
    if (!button) return;
    const action = button.dataset.action;
    if (action === "view") { this._view = button.dataset.view; this._review = null; this._message = null; this._render(); }
    else if (action === "pick") this.shadowRoot.getElementById("file").click();
    else if (action === "rescan") this._rescan();
    else if (action === "review") this._openReview(button.dataset.id);
    else if (action === "cancel") { this._review = null; this._load(); }
    else if (action === "confirm") this._confirm();
  }

  _onChange(event) {
    const target = event.target;
    if (target.id === "file") { this._upload([...target.files]); return; }
    if (!this._review) return;
    if (target.dataset.field) this._review.values[target.dataset.field] = target.value;
    if (target.dataset.supplier !== undefined) this._review.supplier = target.value;
  }

  _onFocus(event) {
    const target = event.target;
    if (target.classList?.contains("hit")) { this._showTip(target); return; }
    if (this._review && target.dataset?.line !== undefined) {
      const index = Number(target.dataset.line);
      this._review.activeLine = index;
      for (const line of this.shadowRoot.querySelectorAll(".text .line")) {
        line.classList.toggle("hit-line", Number(line.dataset.index) === index);
      }
      this.shadowRoot.querySelector(`.text .line[data-index="${index}"]`)?.scrollIntoView({ block: "center", behavior: "smooth" });
    }
  }

  _showTip(rect) {
    this._hideTip();
    const chart = rect.closest(".chart");
    const { label, tip } = JSON.parse(rect.dataset.tip);
    const box = document.createElement("div");
    box.className = "tooltip";
    box.innerHTML = `<b>${esc(label)}</b>${tip.map(([name, value]) => `<div><span>${esc(name)}</span><span>${esc(value)}</span></div>`).join("")}`;
    chart.append(box);
    const x = Number(rect.getAttribute("x")) + Number(rect.getAttribute("width")) / 2;
    const left = Math.min(Math.max(x - box.offsetWidth / 2, 0), chart.clientWidth - box.offsetWidth);
    box.style.left = `${left}px`;
    box.style.top = "0px";
    this._tip = box;
  }

  _hideTip() { this._tip?.remove(); this._tip = null; }

  _onDrag(event) {
    if (!this._isAdmin || this._review) return;
    event.preventDefault();
    if (event.type === "dragover") {
      if (!this._dragging) { this._dragging = true; this.shadowRoot.querySelector(".drop")?.classList.add("over"); }
      return;
    }
    this._dragging = false;
    this.shadowRoot.querySelector(".drop")?.classList.remove("over");
    if (event.type === "drop") this._upload([...event.dataTransfer.files]);
  }

  async _rescan() {
    this._busy = true; this._render();
    try { this._data = await this._hass.callWS({ type: "offgrid2save/rescan" }); }
    catch (err) { this._message = err.message || String(err); }
    this._busy = false; this._render();
  }

  async _upload(files) {
    const pdfs = files.filter((f) => /\.pdf$/i.test(f.name));
    if (!pdfs.length) return;
    const t = this._t;
    this._busy = true; this._message = null; this._view = "bills"; this._render();
    const results = [];
    for (const file of pdfs) {
      const form = new FormData();
      form.append("file", file);
      try {
        const response = await this._hass.fetchWithAuth("/api/offgrid2save/upload", { method: "POST", body: form });
        if (!response.ok) throw new Error(`${response.status}`);
        results.push(await response.json());
      } catch (err) {
        this._message = `${t.upload_failed}: ${file.name} (${err.message})`;
      }
    }
    this._busy = false;
    await this._load();
    if (results.some((r) => r.duplicate)) this._message = t.duplicate;
    const waiting = results.filter((r) => !r.duplicate && ["needs_review", "needs_learning", "unreadable"].includes(r.status));
    if (waiting.length === 1) this._openReview(waiting[0].id);
    else this._render();
  }

  async _openReview(id) {
    try {
      const bill = await this._hass.callWS({ type: "offgrid2save/detail", bill_id: id });
      this._review = { bill, values: { ...bill.values }, supplier: bill.supplier || bill.supplier_name || "", activeLine: null };
      this._message = null;
      this._render();
      this.scrollTop = 0;
    } catch (err) {
      this._message = err.message || String(err);
      this._render();
    }
  }

  async _confirm() {
    const t = this._t, r = this._review;
    for (const input of this.shadowRoot.querySelectorAll("input[data-field]")) r.values[input.dataset.field] = input.value;
    r.supplier = this.shadowRoot.querySelector("input[data-supplier]").value.trim();
    if (r.supplier.length < 2 || REQUIRED.some((key) => r.values[key] === "" || r.values[key] === undefined || r.values[key] === null)) {
      r.error = t.missing; this._render(); return;
    }
    const values = {};
    for (const group of FIELD_GROUPS) {
      for (const [key, kind] of group.fields) {
        const raw = r.values[key];
        if (raw === "" || raw === undefined || raw === null) continue;
        values[key] = kind === "eur" || kind === "kwh" ? Number(raw) : String(raw);
      }
    }
    this._busy = true; r.error = null; this._render();
    try {
      const result = await this._hass.callWS({ type: "offgrid2save/confirm", bill_id: r.bill.id, supplier: r.supplier, values });
      const parts = [];
      if (result.unlocated?.length) parts.push(t.learned_partial(result.unlocated.map((k) => t.field[k] || k).join(", ")));
      else if (result.template_id) parts.push(t.learned_ok);
      if (result.template_id && result.recognizable === false) parts.push(t.not_recognizable);
      this._message = parts.join(" ") || null;
      this._review = null;
      this._view = "bills";
      this._busy = false;
      await this._load();
    } catch (err) {
      this._busy = false;
      r.error = err.message || String(err);
      this._render();
    }
  }
}

customElements.define("offgrid2save-panel", OffGrid2SavePanel);
