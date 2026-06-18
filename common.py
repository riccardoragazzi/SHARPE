"""
common.py
=========
Stato, costanti e funzioni condivise tra le pagine dell'app Sharpe
(Builder e Analisi). Centralizza qui i download con cache, i callback per la
costruzione del portafoglio e la barra laterale dei parametri, così le due
pagine restano snelle e coerenti.
"""

from __future__ import annotations

import json

import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import plotly.io as pio
import streamlit as st

import data as dati
import dataset_composizioni as dsc
import metrics as mtr

ss = st.session_state

# --- D3/D4: grafici con numeri in formato italiano (virgola decimale) e palette
# color-blind friendly (Okabe–Ito). px «cuoce» i colori nelle tracce, quindi la
# palette resta anche col tema di Streamlit; i separatori valgono per assi/tooltip.
PALETTE_CB = ["#0072B2", "#E69F00", "#009E73", "#D55E00", "#CC79A7",
              "#56B4E9", "#F0E442", "#000000"]
try:
    pio.templates["sharpe"] = go.layout.Template(layout=dict(separators=",."))
    pio.templates.default = "plotly+sharpe"
    px.defaults.color_discrete_sequence = PALETTE_CB
except Exception:
    pass

# ---------------------------------------------------------------------------
# Costanti
# ---------------------------------------------------------------------------

VALUTE_COMUNI = ["EUR", "USD", "GBP", "CHF", "JPY"]

# Traduzione dei nomi di settore restituiti da yfinance (in inglese).
SETTORI_IT = {
    "realestate": "Immobiliare",
    "consumer_cyclical": "Consumi ciclici",
    "basic_materials": "Materiali di base",
    "consumer_defensive": "Consumi difensivi",
    "technology": "Tecnologia",
    "communication_services": "Servizi di comunicazione",
    "financial_services": "Servizi finanziari",
    "financial": "Servizi finanziari",
    "utilities": "Utility",
    "industrials": "Industriali",
    "energy": "Energia",
    "healthcare": "Sanità",
}

# Portafoglio di esempio iniziale (ETF reali su Borsa Italiana).
DEFAULT_TICKERS = ["SWDA.MI", "EIMI.MI", "AGGH.MI"]
DEFAULT_PESI = [50.0, 20.0, 30.0]

# Portafogli "famosi" ricostruiti con ETF rappresentativi (USA, storia lunga).
# I pesi sommano a 1. Usati per il confronto nella pagina Builder.
PORTAFOGLI_FAMOSI = {
    "100% MSCI World": {"URTH": 1.0},
    "60/40 (azioni/obbligazioni)": {"VTI": 0.60, "AGG": 0.40},
    "All Weather (Ray Dalio)": {"VTI": 0.30, "TLT": 0.40, "IEI": 0.15, "GLD": 0.075, "DBC": 0.075},
    "Golden Butterfly": {"VTI": 0.20, "IWN": 0.20, "TLT": 0.20, "SHY": 0.20, "GLD": 0.20},
    "Permanent Portfolio": {"VTI": 0.25, "TLT": 0.25, "SHY": 0.25, "GLD": 0.25},
}

# Portafogli "pronti" da caricare nel Builder, con ETF UCITS realmente
# acquistabili (in EUR su Borsa Italiana / Xetra). Pesi in %.
PORTAFOGLI_PRONTI = {
    "3 ETF pigro (Mondo + Emergenti + Obblig.)": {"SWDA.MI": 60.0, "EIMI.MI": 20.0, "AGGH.MI": 20.0},
    "60/40 (azioni/obbligazioni)": {"SWDA.MI": 60.0, "AGGH.MI": 40.0},
    "80/20 (azioni/obbligazioni)": {"SWDA.MI": 80.0, "AGGH.MI": 20.0},
    "All-Weather (semplificato)": {"SWDA.MI": 30.0, "AGGH.MI": 55.0, "SGLD.MI": 15.0},
    "All-world 100% azioni": {"VWCE.DE": 100.0},
}

# Preset "passivi" da mostrare come pulsanti in evidenza nell'onboarding (B4).
PRESET_IN_EVIDENZA = [
    "3 ETF pigro (Mondo + Emergenti + Obblig.)",
    "60/40 (azioni/obbligazioni)",
    "80/20 (azioni/obbligazioni)",
    "All-Weather (semplificato)",
]


# ---------------------------------------------------------------------------
# Funzioni con cache (evitano chiamate di rete ripetute ad ogni interazione)
# ---------------------------------------------------------------------------

@st.cache_data(show_spinner=False)
def carica_dati(tickers, period, start, end, valuta_base, converti):
    """Scarica i prezzi (close aggiustati) e, se richiesto, li converte in EUR."""
    ris = dati.scarica_prezzi(list(tickers), period=period, start=start, end=end)
    if converti and not ris.prezzi.empty:
        ris = dati.converti_in_base(ris, valuta_base, period, start, end)
    else:
        ris.valuta_base = valuta_base
    return ris


@st.cache_data(show_spinner=False)
def carica_settori(tickers):
    """Recupera (dove possibile) i pesi di settore via yfinance, tradotti."""
    out = {}
    for t in tickers:
        sw = dati.scarica_settori(t)
        if sw:
            out[t] = {SETTORI_IT.get(k, k.title()): v for k, v in sw.items()}
    return out


@st.cache_data(show_spinner=False)
def carica_asset_classes(tickers):
    """Recupera (dove possibile) la composizione per classe di attività."""
    out = {}
    for t in tickers:
        ac = dati.scarica_asset_classes(t)
        if ac:
            out[t] = ac
    return out


@st.cache_data(show_spinner=False)
def cerca(query):
    """Ricerca strumenti online (con cache sulla stringa di ricerca)."""
    return dati.cerca_strumenti(query, max_results=12)


@st.cache_data(show_spinner=False)
def nomi_di(tickers):
    """Mappa ticker -> nome reale (con cache)."""
    return dati.nomi_strumenti(list(tickers))


@st.cache_data(show_spinner=False)
def isin_di(ticker):
    """ISIN di un ticker: prima dal dataset interno, poi (best effort) da yfinance."""
    iz = dsc.isin_di(ticker)
    return iz if iz else dati.isin_strumento(ticker)


@st.cache_data(show_spinner=False)
def rendimento_dividendo(ticker):
    """Rendimento da dividendo annuo stimato (con cache)."""
    return dati.rendimento_dividendo(ticker)


@st.cache_data(show_spinner=False)
def ohlcv(ticker, period="max"):
    """Dati OHLCV di un singolo asset per l'analisi tecnica (con cache)."""
    return dati.scarica_ohlcv(ticker, period=period)


def rendimenti_portafoglio_famoso(nome, period, start, end, valuta_base, converti):
    """Serie dei rendimenti giornalieri di un portafoglio famoso (proxy ETF).

    Restituisce ``(serie_rendimenti, mancanti)`` dove ``mancanti`` è la lista
    dei ticker proxy non scaricabili (i pesi vengono riallocati sui presenti).
    """
    pesi_def = PORTAFOGLI_FAMOSI.get(nome, {})
    if not pesi_def:
        return pd.Series(dtype="float64"), []
    ris = carica_dati(tuple(pesi_def.keys()), period, start, end, valuta_base, converti)
    if ris.prezzi.empty:
        return pd.Series(dtype="float64"), list(pesi_def.keys())
    rend = mtr.rendimenti_giornalieri(ris.prezzi)
    presenti = list(rend.columns)
    mancanti = [t for t in pesi_def if t not in presenti]
    pesi = mtr.normalizza_pesi({t: pesi_def[t] for t in presenti}, presenti)
    return mtr.serie_rendimenti_portafoglio(rend, pesi), mancanti


# ---------------------------------------------------------------------------
# Utilità di formattazione / conversione
# ---------------------------------------------------------------------------

def etichetta_corta(nome: str, massimo: int = 38) -> str:
    """Accorcia un nome lungo per legende e assi dei grafici."""
    nome = str(nome)
    return nome if len(nome) <= massimo else nome[: massimo - 1] + "…"


def _num_it(s: str) -> str:
    """Converte un numero formattato 'all'inglese' (1,234.56) in italiano (1.234,56)."""
    return s.replace(",", "§").replace(".", ",").replace("§", ".")


def fmt_pct(x, dec: int = 2) -> str:
    """Percentuale in formato italiano, es. 0.1272 -> '12,72%'."""
    if x is None or (isinstance(x, float) and pd.isna(x)):
        return "n/d"
    return _num_it(f"{x * 100:,.{dec}f}") + "%"


def fmt_eur(x, dec: int = 2) -> str:
    """Importo in euro in formato italiano, es. 1234.56 -> '1.234,56 €'."""
    if x is None or (isinstance(x, float) and pd.isna(x)):
        return "n/d"
    return _num_it(f"{x:,.{dec}f}") + " €"


def fmt_num(x, dec: int = 2) -> str:
    """Numero generico in formato italiano, es. 1.5 -> '1,50'."""
    if x is None or (isinstance(x, float) and pd.isna(x)):
        return "n/d"
    return _num_it(f"{x:,.{dec}f}")


def formatta_metriche(df: pd.DataFrame):
    """Restituisce uno Styler con formattazione (in italiano) % e ratio per la tabella."""
    perc = ["Rend. annuo (CAGR)", "Volatilità annua", "Max drawdown", "Rend. cumulato"]
    ratio = ["Sharpe", "Sortino"]
    fmt = {c: (lambda v: fmt_pct(v)) for c in perc if c in df.columns}
    fmt.update({c: (lambda v: fmt_num(v, 2)) for c in ratio if c in df.columns})
    return df.style.format(fmt)


def comp_to_dataframe(comp: dict) -> pd.DataFrame:
    """Converte la struttura di composizione nel formato lungo (per editor)."""
    righe = []
    for ticker, sezioni in comp.items():
        for tipo in ("paese", "settore"):
            for categoria, peso in sezioni.get(tipo, {}).items():
                righe.append({"Ticker": ticker, "Tipo": tipo, "Categoria": categoria, "Peso": peso})
    if not righe:
        return pd.DataFrame(columns=["Ticker", "Tipo", "Categoria", "Peso"])
    return pd.DataFrame(righe)


def dataframe_to_comp(df: pd.DataFrame) -> dict:
    """Converte il formato lungo (editor) nella struttura di composizione."""
    comp: dict = {}
    for _, r in df.iterrows():
        ticker = str(r.get("Ticker", "")).strip().upper()
        tipo = str(r.get("Tipo", "")).strip().lower()
        categoria = str(r.get("Categoria", "")).strip()
        if not ticker or tipo not in ("paese", "settore") or not categoria:
            continue
        try:
            peso = float(r.get("Peso"))
        except (TypeError, ValueError):
            continue
        comp.setdefault(ticker, {"paese": {}, "settore": {}})
        comp[ticker][tipo][categoria] = peso
    return comp


# ---------------------------------------------------------------------------
# Callback (modificano lo stato PRIMA che i widget vengano ricreati)
# ---------------------------------------------------------------------------

def cb_cerca():
    """Esegue la ricerca online e memorizza i risultati."""
    ss.risultati = cerca(ss.get("query", ""))


def _peso_default_nuovo(n_attuali: int) -> float:
    """Peso di default (quota equa %) per un asset appena aggiunto.

    Evita che i nuovi asset partano da 0% (e quindi vengano ignorati nell'analisi):
    con n asset già presenti, il nuovo riceve 100/(n+1)%. Es. con 19 asset già
    presenti il 20° entra al 5%.
    """
    return round(100.0 / (max(int(n_attuali), 0) + 1), 2)


def cb_aggiungi(symbol: str, nome: str):
    """Aggiunge uno strumento al portafoglio se non già presente."""
    symbol = dati.normalizza_ticker(symbol)
    if symbol and symbol not in ss.selezionati["Ticker"].values:
        peso_nuovo = _peso_default_nuovo(len(ss.selezionati))
        nuova = pd.DataFrame([{"Ticker": symbol, "Nome": nome, "Peso %": peso_nuovo}])
        ss.selezionati = pd.concat([ss.selezionati, nuova], ignore_index=True)


def cb_rimuovi(symbol: str):
    """Rimuove uno strumento dal portafoglio."""
    ss.selezionati = ss.selezionati[ss.selezionati["Ticker"] != symbol].reset_index(drop=True)
    if f"w_{symbol}" in ss:
        del ss[f"w_{symbol}"]


def cb_equipesati():
    """Imposta pesi uguali su tutti gli asset selezionati."""
    tickers = ss.selezionati["Ticker"].tolist()
    n = max(len(tickers), 1)
    val = round(100.0 / n, 2)
    for t in tickers:
        ss[f"w_{t}"] = val


def cb_svuota():
    """Rimuove tutti gli asset selezionati."""
    for t in ss.selezionati["Ticker"].tolist():
        if f"w_{t}" in ss:
            del ss[f"w_{t}"]
    ss.selezionati = ss.selezionati.iloc[0:0]


def cb_applica_pesi(pesi_frazioni: dict):
    """Applica al portafoglio i pesi ottimali (frazioni -> percentuali)."""
    for t, frazione in pesi_frazioni.items():
        if f"w_{t}" in ss or t in ss.selezionati["Ticker"].values:
            ss[f"w_{t}"] = round(float(frazione) * 100.0, 2)


def cb_carica_preset(nome: str):
    """Carica un «portafoglio pronto» sostituendo gli asset/pesi attuali."""
    pesi_def = PORTAFOGLI_PRONTI.get(nome, {})
    if not pesi_def:
        return
    tickers = list(pesi_def.keys())
    nm = nomi_di(tuple(tickers))
    ss.selezionati = pd.DataFrame({
        "Ticker": tickers,
        "Nome": [nm.get(t, t) for t in tickers],
        "Peso %": [pesi_def[t] for t in tickers],
    })
    for k in [k for k in list(ss.keys()) if str(k).startswith("w_")]:
        del ss[k]


def cb_normalizza():
    """Riscala i pesi correnti così che sommino esattamente a 100%."""
    tickers = ss.selezionati["Ticker"].tolist()
    tot = sum(float(ss.get(f"w_{t}", 0.0)) for t in tickers)
    if tot <= 0:
        return
    for t in tickers:
        ss[f"w_{t}"] = round(float(ss.get(f"w_{t}", 0.0)) / tot * 100.0, 2)


# ---------------------------------------------------------------------------
# Stato iniziale e barra laterale dei parametri (condivisa tra le pagine)
# ---------------------------------------------------------------------------

def link_portafoglio(df: pd.DataFrame) -> str:
    """Codifica il portafoglio in stringa per il link condivisibile: 'TICK:peso,...'.

    Esclude gli asset con peso 0 (non avrebbe senso condividerli, e li terrebbe a 0
    a ogni apertura del link).
    """
    parti = [
        f"{r['Ticker']}:{float(r['Peso %']):g}"
        for _, r in df.iterrows()
        if pd.notna(r["Peso %"]) and float(r["Peso %"]) > 0
    ]
    return ",".join(parti)


def _portafoglio_da_link(pf_par: str):
    """Decodifica 'TICK:peso,...' (dal query param ?pf=) in un DataFrame portafoglio."""
    voci = []
    for parte in str(pf_par).split(","):
        if ":" not in parte:
            continue
        t, _, p = parte.partition(":")
        t = t.strip().upper()
        try:
            peso = float(p.replace(",", "."))
        except ValueError:
            continue
        if t:
            voci.append((t, peso))
    if not voci:
        return None
    tickers = [t for t, _ in voci]
    nm = nomi_di(tuple(tickers))
    return pd.DataFrame({
        "Ticker": tickers,
        "Nome": [nm.get(t, t) for t in tickers],
        "Peso %": [p for _, p in voci],
    })


def init_state():
    """Inizializza lo stato condiviso (portafoglio di esempio, composizione).

    Se l'URL contiene un portafoglio condiviso (``?pf=TICK:peso,...``), lo carica
    UNA volta sola (link condivisibile, D5).
    """
    if "selezionati" not in ss:
        nomi0 = nomi_di(tuple(DEFAULT_TICKERS))
        ss.selezionati = pd.DataFrame(
            {
                "Ticker": DEFAULT_TICKERS,
                "Nome": [nomi0.get(t, t) for t in DEFAULT_TICKERS],
                "Peso %": DEFAULT_PESI,
            }
        )
    if "composizione" not in ss:
        ss.composizione = {}
    if "risultati" not in ss:
        ss.risultati = []
    if "costi" not in ss:
        ss.costi = {}

    # Link condivisibile: carica il portafoglio dall'URL (una volta sola).
    if not ss.get("_pf_loaded"):
        ss._pf_loaded = True
        try:
            pf_par = st.query_params.get("pf")
        except Exception:
            pf_par = None
        if pf_par:
            df_link = _portafoglio_da_link(pf_par)
            if df_link is not None and not df_link.empty:
                for k in [k for k in list(ss.keys()) if str(k).startswith("w_")]:
                    del ss[k]
                ss.selezionati = df_link
            # Consuma il link: togli ?pf dall'URL così i reload NON riapplicano i
            # pesi (altrimenti un asset salvato a 0% tornerebbe a 0 a ogni Ctrl+F5).
            try:
                del st.query_params["pf"]
            except Exception:
                pass


def sidebar_parametri():
    """Disegna la barra laterale dei parametri comuni e li salva in session_state.

    Imposta: ``ss.period``, ``ss.data_inizio``, ``ss.data_fine``, ``ss.risk_free``,
    ``ss.valuta_base``, ``ss.converti``.
    """
    st.sidebar.title("⚙️ Parametri")

    with st.sidebar.expander("💾 Salva / carica portafoglio"):
        file_pf = st.file_uploader("Carica un portafoglio (.json)", type=["json"], key="up_pf")
        # Identificatore univoco del file caricato: serve a processarlo UNA volta
        # sola. Senza questo, il file resta nel caricatore e il blocco rigira a ogni
        # rerun (anche spostando uno slider), sovrascrivendo i pesi col contenuto del
        # JSON → non si riuscirebbero più a modificare i pesi a mano.
        _fid = None
        if file_pf is not None:
            _fid = getattr(file_pf, "file_id", None) or (file_pf.name, file_pf.size)
        if file_pf is not None and ss.get("_json_id") != _fid:
            ss["_json_id"] = _fid
            try:
                stato = json.load(file_pf)
                df_caricato = pd.DataFrame(stato["portafoglio"])
                if "Nome" not in df_caricato.columns:
                    nm = nomi_di(tuple(df_caricato["Ticker"]))
                    df_caricato["Nome"] = [nm.get(t, t) for t in df_caricato["Ticker"]]
                for k in [k for k in list(ss.keys()) if str(k).startswith("w_")]:
                    del ss[k]
                ss.selezionati = df_caricato[["Ticker", "Nome", "Peso %"]]
                ss.composizione = stato.get("composizione", {})
                st.success("Portafoglio caricato.")
            except Exception as exc:
                st.error(f"File non valido: {exc}")

    st.sidebar.subheader("Intervallo temporale")
    modo = st.sidebar.radio("Modalità", ["Periodo rapido", "Intervallo personalizzato"], key="modo_periodo")
    period, data_inizio, data_fine = None, None, None
    if modo == "Periodo rapido":
        period = st.sidebar.selectbox("Periodo", ["1y", "2y", "3y", "5y", "10y", "max"], index=3, key="sel_period")
    else:
        oggi = pd.Timestamp.today().normalize()
        data_inizio = st.sidebar.date_input("Data inizio", oggi - pd.Timedelta(days=5 * 365), key="d_inizio")
        data_fine = st.sidebar.date_input("Data fine", oggi, key="d_fine")

    st.sidebar.subheader("Altri parametri")
    rf_perc = st.sidebar.number_input(
        "Tasso risk-free annuo (%)", value=3.0, step=0.25, format="%.2f", key="rf",
        help="Rendimento di un investimento «senza rischio» (es. titoli di Stato a breve). "
             "Serve per calcolare Sharpe e Sortino.",
    )
    orizzonte = st.sidebar.number_input(
        "Orizzonte d'investimento (anni)", value=10, min_value=1, max_value=40, step=1, key="orizzonte",
        help="Per quanti anni pensi di tenere l'investimento. Usato nel riepilogo automatico "
             "e nella proiezione a obiettivo. Più è lungo, più le oscillazioni di breve contano poco.",
    )
    infl_perc = st.sidebar.number_input(
        "Inflazione annua attesa (%)", value=2.0, min_value=0.0, max_value=15.0, step=0.5, format="%.1f",
        key="infl_perc",
        help="Quanto crescono i prezzi ogni anno. Serve per i «valori reali» (potere d'acquisto).",
    )
    reali = st.sidebar.checkbox(
        "Ragiona al netto dell'inflazione (valori reali)", value=False, key="reali",
        help="Se attivo, rendimenti e proiezioni sono espressi in **€ di oggi** (tolta l'inflazione): "
             "più realistico su 10–20 anni.",
    )
    valuta_base = st.sidebar.selectbox("Valuta base", VALUTE_COMUNI, index=0, key="valuta")
    converti = st.sidebar.checkbox(f"Converti tutto in {valuta_base}", value=True, key="conv")

    st.sidebar.divider()
    if st.sidebar.button("🔄 Aggiorna dati (svuota cache)", width="stretch"):
        st.cache_data.clear()
        st.rerun()

    # Salvataggio portafoglio.
    stato_export = {
        "portafoglio": ss.selezionati.to_dict(orient="list"),
        "composizione": ss.composizione,
    }
    st.sidebar.download_button(
        "⬇️ Salva portafoglio (.json)",
        data=json.dumps(stato_export, ensure_ascii=False, indent=2),
        file_name="portafoglio.json",
        mime="application/json",
        width="stretch",
    )

    # Memorizza i parametri per le pagine.
    ss.period = period
    ss.data_inizio = pd.Timestamp(data_inizio) if data_inizio else None
    ss.data_fine = pd.Timestamp(data_fine) if data_fine else None
    ss.risk_free = rf_perc / 100.0
    ss.inflazione = infl_perc / 100.0
    # ss.reali è già impostato dal widget (key="reali"): non va riassegnato.
    ss.valuta_base = valuta_base
    ss.converti = converti


def portafoglio_pulito() -> pd.DataFrame:
    """Restituisce il DataFrame del portafoglio ripulito (ticker validi, unici)."""
    sel = ss.selezionati.copy()
    sel["Ticker"] = sel["Ticker"].astype(str).str.strip().str.upper()
    sel = sel[sel["Ticker"] != ""].drop_duplicates(subset="Ticker").reset_index(drop=True)
    return sel


def mostra_avvisi_qualita(prezzi: pd.DataFrame):
    """Mostra gli avvisi di qualità dei dati (storico, buchi, anomalie)."""
    for livello, msg in dati.controlla_qualita(prezzi):
        (st.warning if livello == "warning" else st.info)("🔎 " + msg)


def composizione_effettiva(tickers) -> dict:
    """Composizione paese/settore per i ticker: manuale (override) o dataset interno.

    Se l'utente ha inserito a mano (o da CSV) la composizione di un asset, quella
    ha la precedenza; altrimenti si usa il dataset interno ``dataset_composizioni``.
    """
    out = {}
    for t in tickers:
        manuale = ss.composizione.get(t, {})
        if manuale.get("paese") or manuale.get("settore"):
            out[t] = {"paese": dict(manuale.get("paese", {})),
                      "settore": dict(manuale.get("settore", {}))}
        else:
            nota = dsc.composizione_nota(t)
            if nota:
                out[t] = nota
    return out


def inietta_css_mobile():
    """Inietta CSS «responsive» per migliorare la resa su SMARTPHONE.

    Tutte le regole stanno dentro una media query ``max-width: 640px``: valgono
    quindi SOLO su schermi piccoli (telefoni), mentre su desktop l'aspetto resta
    identico a prima. Va chiamata una volta sola da ``app.py``, così vale per
    entrambe le pagine. L'idea chiave: su telefono le colonne affiancate vanno
    «a capo» invece di schiacciarsi, e le metriche si dispongono 2 per riga.
    """
    st.markdown(
        """
        <style>
        @media (max-width: 640px) {
            /* Contenuto un po' più in alto e con margini laterali più stretti. */
            [data-testid="stMainBlockContainer"] {
                padding-top: 3rem !important;
                padding-left: 0.8rem !important;
                padding-right: 0.8rem !important;
            }
            /* Titoli più piccoli su telefono, così non occupano troppe righe. */
            h1 { font-size: 1.7rem !important; line-height: 1.2 !important; }
            h2 { font-size: 1.35rem !important; }
            h3 { font-size: 1.15rem !important; }

            /* Le colonne affiancate vanno «a capo» invece di restringersi. */
            [data-testid="stHorizontalBlock"] { flex-wrap: wrap !important; }
            /* Default: ogni colonna a tutta larghezza (grafici, ricerca, righe pesi). */
            [data-testid="stColumn"] { min-width: 100% !important; }
            /* Eccezione: le colonne con una METRICA vanno 2 per riga (più leggibili). */
            [data-testid="stColumn"]:has([data-testid="stMetric"]) {
                min-width: calc(50% - 0.5rem) !important;
                flex: 1 1 calc(50% - 0.5rem) !important;
            }
            /* Numeri ed etichette delle metriche più piccoli, così non si tagliano. */
            [data-testid="stMetricValue"] { font-size: 1.25rem !important; }
            [data-testid="stMetricLabel"] { font-size: 0.8rem !important; }

            /* Le tabelle larghe restano scorribili lateralmente (comportamento nativo). */
            [data-testid="stDataFrame"] { overflow-x: auto !important; }
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


def mostra_descrizione_app():
    """Descrizione sintetica dell'app: cos'è e cosa puoi farci.

    Serve a tre scopi insieme: (1) chi arriva la prima volta capisce subito l'app;
    (2) un'AI con navigazione che apre il link coglie al volo di cosa si tratta e
    può dare un parere sensato; (3) Google usa questo testo in cima come descrizione
    nei risultati di ricerca. Espansa al primo accesso, poi richiudibile.
    """
    espandi = not ss.get("descrizione_vista", False)
    with st.expander("ℹ️ Cos'è Sharpe e cosa puoi fare", expanded=espandi):
        st.markdown(
            "**Sharpe** è un'app gratuita e **didattica** per analizzare **ETF e indici** e "
            "costruire un **portafoglio** di lungo periodo (pensata per investitori passivi). "
            "Tutto in italiano, con ogni metrica spiegata in parole semplici.\n\n"
            "**Cosa puoi fare:**\n"
            "- 🔎 **Cercare** ETF/indici per nome, ticker o ISIN e comporre un portafoglio "
            "(o partire da **portafogli pronti**).\n"
            "- 📊 **Misurare rischio e rendimento**: CAGR, volatilità, **Sharpe**, Sortino, "
            "max drawdown, correlazioni, contributo al rischio.\n"
            "- 🌍 **Diversificazione** per asset class, **paese** e **settore**, con avvisi "
            "sulle sovrapposizioni.\n"
            "- 💶 **PAC** (versamenti periodici), 🎯 **Obiettivo** di capitale (proiezioni "
            "Monte Carlo), 💰 **costi e tasse**, 💸 **dividendi**, ♻️ **ribilanciamento**, "
            "🧮 **ottimizzazione**.\n"
            "- 📈 **Analisi tecnica** di qualunque asset: candele, volumi, medie mobili, RSI.\n\n"
            "⚠️ Strumento di **analisi/educativo**: non è consulenza finanziaria. Dati da Yahoo Finance."
        )
        ss.descrizione_vista = True


def mostra_onboarding():
    """Mini guida «come si usa in 3 passi» (espansa solo la prima volta)."""
    espandi = not ss.get("onboarding_visto", False)
    with st.expander("👋 Come si usa in 3 passi", expanded=espandi):
        st.markdown(
            "1. **Costruisci il portafoglio** (pagina 🧱 *Builder*): cerca ETF per nome / ticker / ISIN "
            "oppure carica un **portafoglio pronto**, poi regola i pesi.\n"
            "2. **Leggi le analisi**: rischio e diversificazione (paesi/settori), e i piani — "
            "**💶 PAC** (versamenti periodici) e **🎯 Obiettivo** (quanto versare per una cifra).\n"
            "3. **Approfondisci un singolo asset** nella pagina **📈 Analisi tecnica** "
            "(anche asset non in portafoglio).\n\n"
            "Nella **barra laterale** imposti periodo, orizzonte, valuta e inflazione. "
            "📱 Da telefono: apri il menu **☰** in alto a sinistra per i parametri; nel "
            "Builder scegli cosa vedere dal menu a tendina **«Sezione»**. "
            "Tutto è a scopo **didattico**, non è consulenza finanziaria."
        )
        ss.onboarding_visto = True


def mostra_glossario():
    """Glossario didattico delle metriche principali (in italiano semplice)."""
    with st.expander("📖 Glossario delle metriche (cosa significano e cosa è «buono»)"):
        st.markdown(
            "- **Rendimento annuo (CAGR)** — di quanto è cresciuto in media ogni anno. "
            "Più alto è meglio, ma va guardato **insieme al rischio**.\n"
            "- **Volatilità annua** — quanto oscilla il valore: più bassa = più tranquillo. "
            "Indicativo: sotto 8% basso, 8–15% medio, oltre 15% alto.\n"
            "- **Sharpe** — rendimento ottenuto per ogni unità di rischio (oltre il risk-free). "
            "Indicativo: **>1 buono, >2 ottimo, <0** il rischio non è stato ripagato.\n"
            "- **Sortino** — come lo Sharpe, ma considera solo le oscillazioni **verso il basso** "
            "(le perdite). Più alto è meglio.\n"
            "- **Max drawdown** — la perdita massima dal punto più alto a quello più basso "
            "(es. −30% = a un certo punto avresti perso il 30% dal picco). Più vicino a 0 è meglio.\n"
            "- **Rendimento cumulato** — quanto hai guadagnato in **totale** nel periodo.\n\n"
            "_Valori indicativi e didattici: dipendono dal periodo analizzato e non sono garanzie._"
        )


def mostra_box_rischio_cambio():
    """Box didattico sul rischio cambio: valuta di QUOTAZIONE vs del SOTTOSTANTE."""
    with st.expander("💱 Rischio cambio: cosa significa la «valuta»"):
        st.markdown(
            "- La **valuta di quotazione** è quella in cui compri l'ETF in borsa (es. **EUR** su Borsa "
            "Italiana): è quella mostrata qui sopra come «valuta nativa».\n"
            "- La **valuta del sottostante** è quella degli asset che l'ETF contiene davvero (es. un ETF "
            "sul **MSCI World** quotato in EUR possiede comunque molte azioni in **USD** e altre valute).\n"
            "- Perciò, anche comprando in EUR, sei **esposto al cambio**: se il dollaro si indebolisce "
            "sull'euro il valore scende (e viceversa), a meno che l'ETF non sia a **cambio coperto (hedged)**.\n\n"
            "_Qui i prezzi vengono convertiti nella tua valuta base solo per confrontarli; la copertura "
            "valutaria dipende dal singolo ETF (vedi nome/factsheet, es. «EUR Hedged»)._"
        )


def mostra_footer_disclaimer():
    """Footer ricorrente col disclaimer, da mostrare in fondo a ogni pagina/sezione."""
    st.divider()
    st.caption(
        "⚠️ **Sharpe** è uno strumento di **analisi e didattico**: non è consulenza finanziaria né "
        "raccomandazione di investimento. Dati da **Yahoo Finance** (possibili errori o ritardi). "
        "I rendimenti passati non garantiscono quelli futuri."
    )


def risposta_assistente(domanda: str, dati: dict) -> str:
    """Aiutante guidato SENZA AI esterna (nessuna chiave, nessuna rete).

    Funzione **pura**: abbina la ``domanda`` per parole chiave a una risposta
    didattica in italiano, costruita dai numeri **già calcolati** passati in
    ``dati`` (met_pf, riepilogo, indici di diversificazione, asset che pesa di
    più sul rischio...). Non dà MAI consigli di investimento.
    """
    d = (domanda or "").lower().strip()
    met = dati.get("met_pf", {}) or {}
    riep = dati.get("riep", {}) or {}

    def _num(chiave, fmt):
        v = met.get(chiave)
        if v is None or (isinstance(v, float) and pd.isna(v)):
            return "n/d"
        return fmt.format(v)

    # --- Guardrail: niente consigli di investimento ---
    parole_consiglio = ("conviene", "compro", "comprare", "vendo", "vendere", "investo",
                        "investire", "consigli", "consiglio", "cosa compro", "su cosa punto",
                        "dove investo", "devo comprare", "devo vendere")
    if any(p in d for p in parole_consiglio):
        return (
            "Non posso darti **consigli di investimento** né dirti cosa comprare o vendere: "
            "Sharpe è uno strumento **didattico**. Posso però spiegarti i **tuoi numeri** (rischio, "
            "diversificazione, Sharpe…), così decidi in autonomia. Prova: *«com'è il mio rischio?»* "
            "oppure *«quanto sono diversificato?»*."
        )

    # --- Quale asset pesa di più sul rischio (prima di "rischio" generico) ---
    if "pesa" in d or "contribut" in d or ("asset" in d and "rischio" in d):
        nome = dati.get("top_rischio_nome")
        quota = dati.get("top_rischio_quota")
        if nome and quota is not None:
            return (
                f"L'asset che incide di più sul rischio è **{nome}**, responsabile di circa "
                f"**{quota:.0%}** della volatilità del portafoglio. Se una sola voce pesa molto, il "
                "portafoglio è **concentrato**: vedi *Contributo al rischio* nella sezione **💼 Portafoglio**."
            )

    # --- Diversificazione (geografica + settoriale) ---
    if any(k in d for k in ("diversif", "concentr", "paesi", "paese", "settor", "geografic", "distribu")):
        dp = dati.get("div_paese", {}) or {}
        dse = dati.get("div_settore", {}) or {}
        righe = [
            f"**Diversificazione complessiva**: {riep.get('diversificazione', 'n/d')} "
            f"(su {dati.get('n_asset', '?')} asset)."
        ]
        if dp.get("valido"):
            righe.append(
                f"- 🌍 **Geografica**: {dp['livello']} ({dp['punteggio']}/100). "
                f"Quota principale **{dp['top_categoria']} {dp['top_peso']:.0%}**, "
                f"≈ {dp['numero_effettivo']:.1f} aree."
            )
        if dse.get("valido"):
            righe.append(
                f"- 🏭 **Settoriale**: {dse['livello']} ({dse['punteggio']}/100). "
                f"Quota principale **{dse['top_categoria']} {dse['top_peso']:.0%}**, "
                f"≈ {dse['numero_effettivo']:.1f} settori."
            )
        if not dp.get("valido") and not dse.get("valido"):
            righe.append("_Composizione per paese/settore non disponibile per questi asset._")
        righe.append(
            "\nPiù alto il punteggio, meno dipendi da un singolo paese/settore. "
            "Dettagli e grafici nella sezione **🌍 Allocazione**."
        )
        return "\n".join(righe)

    # --- Rischio / volatilità ---
    if "rischio" in d or "volatil" in d or "oscilla" in d:
        return (
            f"Il tuo rischio è **{riep.get('rischio', 'n/d')}**: la **volatilità annua** è "
            f"**{_num('Volatilità annua (covarianza)', '{:.1%}')}** "
            "(sotto 8% = basso, 8–15% = medio, oltre 15% = alto). La perdita massima storica "
            f"(max drawdown) è stata **{_num('Max drawdown', '{:.1%}')}**. La volatilità misura "
            "**quanto oscilla** il valore: più è alta, più sali e scendi nel tempo."
        )

    # --- Metriche specifiche ---
    if "sharpe" in d:
        return (
            "**Sharpe** = rendimento ottenuto per ogni unità di rischio (oltre il risk-free). "
            "Indicativo: >1 buono, >2 ottimo, <0 il rischio non è stato ripagato. "
            f"Il tuo è **{_num('Sharpe', '{:.2f}')}**."
        )
    if "sortino" in d:
        return (
            "**Sortino** = come lo Sharpe, ma conta solo le oscillazioni **verso il basso** "
            f"(le perdite). Più alto è meglio. Il tuo è **{_num('Sortino', '{:.2f}')}**."
        )
    if "drawdown" in d or "perdita massima" in d:
        return (
            "**Max drawdown** = la perdita massima dal punto più alto a quello più basso "
            "(es. −30% = a un certo punto avresti perso il 30% dal picco). Più vicino a 0 è meglio. "
            f"Il tuo è **{_num('Max drawdown', '{:.1%}')}**."
        )
    if "cagr" in d or "rendiment" in d or "guadagn" in d:
        return (
            "**Rendimento annuo (CAGR)** = quanto è cresciuto in media ogni anno. Il tuo è "
            f"**{_num('Rend. annuo (CAGR)', '{:.1%}')}**; il rendimento **cumulato** nel periodo è "
            f"**{_num('Rend. cumulato', '{:.1%}')}**. Va sempre letto **insieme al rischio**."
        )

    # --- Sezioni specifiche dell'app ---
    if "pac" in d:
        return ("Il **💶 PAC** simula versamenti periodici (es. ogni mese) e li confronta con un "
                "investimento unico. Apri la sezione **💶 PAC** dal menu in alto.")
    if "obiettiv" in d:
        return ("La sezione **🎯 Obiettivo** stima quanto versare per raggiungere una cifra, con la "
                "probabilità che scegli tu (simulazione Monte Carlo).")
    if "costi" in d or "tass" in d:
        return ("In **💰 Costi e tasse** vedi l'impatto di TER e tasse (capital gain, bollo) sul "
                "rendimento nel tempo.")
    if "dividend" in d:
        return ("In **💸 Dividendi** vedi la rendita lorda/netta stimata dei tuoi ETF a distribuzione.")
    if "ribilanc" in d:
        return ("In **♻️ Ribilanciamento** confronti il mantenere i pesi costanti (ribilanciando) col "
                "lasciarli correre (buy & hold).")
    if "ottimizz" in d:
        return ("In **🧮 Ottimizzazione** vedi pesi «ottimali» secondo vari criteri (minima varianza, "
                "max Sharpe…). ⚠️ Si basa sul **passato**: non garantisce il futuro.")

    # --- Guida generale / "cosa sai fare" ---
    if any(k in d for k in ("come funziona", "come uso", "come si usa", "guida", "aiuto",
                            "cosa puoi", "cosa sai", "aiutami", "ciao")):
        return (
            "Posso aiutarti così:\n"
            "- **«Quanto sono diversificato?»** — geografica e settoriale.\n"
            "- **«Com'è il mio rischio?»** — volatilità e perdita massima.\n"
            "- **«Cosa significa Sharpe / Sortino / CAGR / drawdown?»** — più il tuo valore.\n"
            "- **«Quale asset pesa di più sul rischio?»**\n\n"
            "Per costruire il portafoglio usa **💼 Portafoglio**; per i piani **💶 PAC** e **🎯 Obiettivo**; "
            "per paesi/settori **🌍 Allocazione**. Cambi sezione dal menu **«📂 Sezione»** in alto."
        )

    # --- Fallback ---
    return (
        "Non sono sicuro di aver capito 🤔. Posso parlarti di: **diversificazione**, **rischio**, "
        "**Sharpe / Sortino / CAGR / drawdown**, **quale asset pesa di più sul rischio** e **come si usa "
        "l'app**. Prova con una di queste, oppure clicca una *domanda rapida*."
    )


# ---------------------------------------------------------------------------
# Componente UI: "lettura statistica" (semaforo + indicatori)
# ---------------------------------------------------------------------------

def _segno(x: float) -> str:
    """Traduce un sotto-segnale [-1,+1] in una parola con icona."""
    if x is None or (isinstance(x, float) and np.isnan(x)):
        return "—"
    if x > 0.15:
        return "favorevole ✅"
    if x < -0.15:
        return "sfavorevole ⚠️"
    return "neutro ➖"


# Benchmark azionario globale per l'indicatore generale di mercato (in ordine
# di preferenza: si usa il primo che restituisce dati).
BENCHMARK_MERCATO = ["ACWI", "URTH", "^GSPC", "SWDA.MI"]


def _figura_gauge(valore: float, chiave: str):
    """Crea il gauge 1–5 colorato (rosso→grigio→verde) per il semaforo."""
    fig = go.Figure(go.Indicator(
        mode="gauge+number",
        value=round(valore, 2),
        number={"suffix": " / 5", "font": {"size": 34}},
        gauge={
            "axis": {"range": [1, 5], "tickvals": [1, 2, 3, 4, 5]},
            "bar": {"color": "rgba(0,0,0,0)"},
            "steps": [
                {"range": [1, 1.8], "color": "#b3261e"},
                {"range": [1.8, 2.6], "color": "#e8705f"},
                {"range": [2.6, 3.4], "color": "#bdbdbd"},
                {"range": [3.4, 4.2], "color": "#7fc97f"},
                {"range": [4.2, 5], "color": "#2e7d32"},
            ],
            "threshold": {"line": {"color": "black", "width": 5}, "thickness": 0.9, "value": valore},
        },
    ))
    fig.update_layout(height=240, margin=dict(t=10, b=10, l=20, r=20))
    return fig


def mostra_semaforo_mercato():
    """Indicatore GENERALE di mercato (risk-on / risk-off), 1–5.

    Risponde a: «conviene statisticamente investire ora su asset più rischiosi
    (azioni) o più prudenti (obbligazioni/liquidità)?». È **indipendente dal
    portafoglio**: si calcola su un benchmark azionario globale (vedi
    ``BENCHMARK_MERCATO``). Mostra una barra colorata sempre visibile e un
    pannello con il gauge e i dettagli.
    """
    close, usato = None, None
    for b in BENCHMARK_MERCATO:
        # Finestra ampia ma fissa (10 anni): basta a SMA 200gg, momentum 126gg e
        # mediana della volatilità, ed evita di scaricare tutto lo storico "max"
        # (che rallentava il primo disegno della pagina).
        full = ohlcv(b, "10y")
        if not full.empty and "Close" in full.columns and len(full["Close"].dropna()) > 30:
            close, usato = full["Close"], b
            break
    if close is None:
        st.caption("ℹ️ Indicatore di mercato non disponibile al momento (dati assenti).")
        return

    sem = mtr.semaforo_rischio(close)
    st.markdown(
        f"<div style='background:{sem['colore']};padding:10px 18px;border-radius:10px;"
        f"color:white;font-size:17px'>🌍 <b>Clima di mercato (risk-on / risk-off):</b> "
        f"&nbsp;<b>{sem['banda']}/5</b> — {sem['etichetta']}</div>",
        unsafe_allow_html=True,
    )
    with st.expander("ℹ️ Meglio investire ora su asset più rischiosi o più prudenti? (indicatore generale di mercato)"):
        st.caption(
            "Indicatore **generale e indipendente dal tuo portafoglio**: stima, su base statistica, "
            "se il contesto di mercato è favorevole agli asset rischiosi (azioni) o a quelli prudenti "
            "(obbligazioni/liquidità), con orizzonte orientativo di **circa 1 anno**. "
            f"Calcolato sull'azionario globale (benchmark: {usato})."
        )
        cg, ci = st.columns([1, 1])
        with cg:
            st.plotly_chart(_figura_gauge(sem["valore"], "mercato"), width="stretch", key="gauge_mercato")
        with ci:
            st.markdown(
                f"<div style='background:{sem['colore']};padding:16px 18px;border-radius:12px;"
                f"color:white;text-align:center'>"
                f"<div style='font-size:42px;font-weight:800;line-height:1'>{sem['banda']}/5</div>"
                f"<div style='font-size:15px;margin-top:6px'>{sem['etichetta']}</div></div>",
                unsafe_allow_html=True,
            )
            st.caption(
                f"Componenti — Trend: {_segno(sem['trend'])} · "
                f"Volatilità: {_segno(sem['volatilita'])} · "
                f"Momentum: {_segno(sem['momentum'])}"
            )
        st.caption(
            "Lettura: **5 = meglio asset rischiosi** (azioni) · 3 = neutro · **1 = meglio asset prudenti**. "
            "Basato su trend (vs media 200gg), regime di volatilità e momentum a 6 mesi. "
            "⚠️ Indicazione statistica/storica a scopo **didattico**, non un consiglio di investimento; "
            "i mercati possono comportarsi diversamente."
        )


def mostra_lettura_statistica(prezzo: pd.Series, rendimenti: pd.Series, risk_free: float, chiave: str = ""):
    """Indicatori statistici specifici di un asset o del portafoglio.

    (Il semaforo risk-on/off NON è qui: è un indicatore generale di mercato, in
    cima all'app — vedi :func:`mostra_semaforo_mercato`.)

    - ``prezzo``: serie di livelli (prezzo dell'asset o ricchezza del portafoglio),
      per valutazione caro/economico e RSI;
    - ``rendimenti``: serie dei rendimenti, per il vantaggio statistico.
    """
    val = mtr.valutazione_prezzo(prezzo)
    rsi_serie = mtr.rsi(prezzo, 14).dropna()
    rsi_val = float(rsi_serie.iloc[-1]) if not rsi_serie.empty else float("nan")
    van = mtr.vantaggio_statistico(rendimenti, risk_free)

    st.markdown("#### 🔎 Indicatori statistici")
    a, b, c = st.columns(3)
    premio = val.get("premio", np.nan)
    a.metric(
        "Prezzo vs media storica", val["giudizio_breve"],
        f"{premio:+.1%}" if premio is not None and not np.isnan(premio) else None,
        delta_color="off",
    )
    b.metric("RSI (14)", f"{rsi_val:.0f}" if not np.isnan(rsi_val) else "—",
             mtr.giudizio_rsi(rsi_val), delta_color="off")
    sh = van.get("sharpe", np.nan)
    c.metric("Vantaggio statistico", van["giudizio"],
             f"Sharpe {sh:.2f}" if sh is not None and not np.isnan(sh) else None, delta_color="off")

    z = val.get("z", np.nan)
    win = van.get("win_rate", np.nan)
    win_txt = f"{win:.0%}" if win is not None and not np.isnan(win) else "n/d"
    z_txt = f"{z:.2f}" if z is not None and not np.isnan(z) else "n/d"
    st.caption(
        f"«Prezzo vs media»: quanto il livello attuale è sopra/sotto la propria media storica "
        f"(z-score {z_txt}). «Vantaggio statistico»: dallo Sharpe storico; finestre di 1 anno "
        f"chiuse in positivo: {win_txt}. "
        "⚠️ Indicatori statistici/storici a scopo **didattico**, non consigli di investimento."
    )
