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
import plotly.graph_objects as go
import streamlit as st

import data as dati
import dataset_composizioni as dsc
import metrics as mtr

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
    "3-fund (Mondo + Emergenti + Obblig.)": {"SWDA.MI": 60.0, "EIMI.MI": 20.0, "AGGH.MI": 20.0},
    "60/40 (azioni/obbligazioni)": {"SWDA.MI": 60.0, "AGGH.MI": 40.0},
    "All-world 100% azioni": {"VWCE.DE": 100.0},
}


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
    if "costi" not in ss:
        ss.costi = {}


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
            "📱 Da telefono: apri il menu in alto a sinistra e scorri le schede in orizzontale. "
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
        full = ohlcv(b, "max")
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
