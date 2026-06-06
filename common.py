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

import pandas as pd
import streamlit as st

import data as dati

ss = st.session_state

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
def cerca(query):
    """Ricerca strumenti online (con cache sulla stringa di ricerca)."""
    return dati.cerca_strumenti(query, max_results=12)


@st.cache_data(show_spinner=False)
def nomi_di(tickers):
    """Mappa ticker -> nome reale (con cache)."""
    return dati.nomi_strumenti(list(tickers))


@st.cache_data(show_spinner=False)
def ohlcv(ticker, period="max"):
    """Dati OHLCV di un singolo asset per l'analisi tecnica (con cache)."""
    return dati.scarica_ohlcv(ticker, period=period)


# ---------------------------------------------------------------------------
# Utilità di formattazione / conversione
# ---------------------------------------------------------------------------

def etichetta_corta(nome: str, massimo: int = 38) -> str:
    """Accorcia un nome lungo per legende e assi dei grafici."""
    nome = str(nome)
    return nome if len(nome) <= massimo else nome[: massimo - 1] + "…"


def formatta_metriche(df: pd.DataFrame):
    """Restituisce uno Styler con formattazione % e ratio per la tabella."""
    perc = ["Rend. annuo (CAGR)", "Volatilità annua", "Max drawdown", "Rend. cumulato"]
    ratio = ["Sharpe", "Sortino"]
    fmt = {c: "{:.2%}" for c in perc if c in df.columns}
    fmt.update({c: "{:.2f}" for c in ratio if c in df.columns})
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


def cb_aggiungi(symbol: str, nome: str):
    """Aggiunge uno strumento al portafoglio se non già presente."""
    symbol = dati.normalizza_ticker(symbol)
    if symbol and symbol not in ss.selezionati["Ticker"].values:
        nuova = pd.DataFrame([{"Ticker": symbol, "Nome": nome, "Peso %": 0.0}])
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


# ---------------------------------------------------------------------------
# Stato iniziale e barra laterale dei parametri (condivisa tra le pagine)
# ---------------------------------------------------------------------------

def init_state():
    """Inizializza lo stato condiviso (portafoglio di esempio, composizione)."""
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


def sidebar_parametri():
    """Disegna la barra laterale dei parametri comuni e li salva in session_state.

    Imposta: ``ss.period``, ``ss.data_inizio``, ``ss.data_fine``, ``ss.risk_free``,
    ``ss.valuta_base``, ``ss.converti``.
    """
    st.sidebar.title("⚙️ Parametri")

    with st.sidebar.expander("💾 Salva / carica portafoglio"):
        file_pf = st.file_uploader("Carica un portafoglio (.json)", type=["json"], key="up_pf")
        if file_pf is not None:
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
    rf_perc = st.sidebar.number_input("Tasso risk-free annuo (%)", value=3.0, step=0.25, format="%.2f", key="rf")
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
    ss.valuta_base = valuta_base
    ss.converti = converti


def portafoglio_pulito() -> pd.DataFrame:
    """Restituisce il DataFrame del portafoglio ripulito (ticker validi, unici)."""
    sel = ss.selezionati.copy()
    sel["Ticker"] = sel["Ticker"].astype(str).str.strip().str.upper()
    sel = sel[sel["Ticker"] != ""].drop_duplicates(subset="Ticker").reset_index(drop=True)
    return sel
