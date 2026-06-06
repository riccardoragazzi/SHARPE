"""
app.py
======
Interfaccia Streamlit per l'analisi di ETF / indici e di un portafoglio.

Avvio:
    streamlit run app.py
    (oppure: python -m streamlit run app.py)

Il portafoglio si costruisce **dentro l'app**: si cercano gli ETF/indici per
nome o ticker (dati da Yahoo Finance), si selezionano e si assegnano i pesi.
Nelle analisi gli asset sono mostrati con il loro **nome reale** (non il ticker).

L'app è organizzata in tab:
1. Singoli asset  -> metriche per asset, andamento normalizzato, drawdown
2. Portafoglio    -> metriche di portafoglio, confronto, correlazioni, rischio
3. Allocazione    -> distribuzione per paese e per settore (composizione)
4. Ottimizzazione -> minima varianza e frontiera efficiente (extra)

Strumento a scopo di analisi / didattico: NON costituisce consulenza
finanziaria.
"""

from __future__ import annotations

import json

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

import data as dati
import metrics as mtr

# ---------------------------------------------------------------------------
# Configurazione pagina e costanti
# ---------------------------------------------------------------------------

st.set_page_config(page_title="Sharpe — Analisi ETF & Portafoglio", layout="wide")

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

ss = st.session_state


# ---------------------------------------------------------------------------
# Funzioni con cache (evitano chiamate di rete ripetute ad ogni interazione)
# ---------------------------------------------------------------------------

@st.cache_data(show_spinner=False)
def carica_dati(tickers, period, start, end, valuta_base, converti):
    """Scarica i prezzi e (opzionalmente) li converte nella valuta base."""
    ris = dati.scarica_prezzi(list(tickers), period=period, start=start, end=end)
    if converti and not ris.prezzi.empty:
        ris = dati.converti_in_base(ris, valuta_base, period, start, end)
    else:
        ris.valuta_base = valuta_base
    return ris


@st.cache_data(show_spinner=False)
def carica_settori(tickers):
    """Recupera (dove possibile) i pesi di settore via yfinance."""
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


# ---------------------------------------------------------------------------
# Utilità
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
# Stato iniziale
# ---------------------------------------------------------------------------

if "selezionati" not in ss:
    # Portafoglio di esempio iniziale, con i nomi reali già risolti.
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
# Sidebar: parametri di analisi
# ---------------------------------------------------------------------------

st.sidebar.title("⚙️ Parametri")

with st.sidebar.expander("💾 Salva / carica portafoglio"):
    file_pf = st.file_uploader("Carica un portafoglio (.json)", type=["json"], key="up_pf")
    if file_pf is not None:
        try:
            stato = json.load(file_pf)
            df_caricato = pd.DataFrame(stato["portafoglio"])
            # Compatibilità: se manca la colonna Nome, la si risolve online.
            if "Nome" not in df_caricato.columns:
                nm = nomi_di(tuple(df_caricato["Ticker"]))
                df_caricato["Nome"] = [nm.get(t, t) for t in df_caricato["Ticker"]]
            # Pulisce eventuali stati dei pesi precedenti.
            for k in [k for k in list(ss.keys()) if str(k).startswith("w_")]:
                del ss[k]
            ss.selezionati = df_caricato[["Ticker", "Nome", "Peso %"]]
            ss.composizione = stato.get("composizione", {})
            st.success("Portafoglio caricato.")
        except Exception as exc:
            st.error(f"File non valido: {exc}")

st.sidebar.subheader("Intervallo temporale")
modo = st.sidebar.radio("Modalità", ["Periodo rapido", "Intervallo personalizzato"])
period, data_inizio, data_fine = None, None, None
if modo == "Periodo rapido":
    period = st.sidebar.selectbox("Periodo", ["1y", "2y", "3y", "5y", "10y", "max"], index=3)
else:
    oggi = pd.Timestamp.today().normalize()
    data_inizio = st.sidebar.date_input("Data inizio", oggi - pd.Timedelta(days=5 * 365))
    data_fine = st.sidebar.date_input("Data fine", oggi)

st.sidebar.subheader("Altri parametri")
rf_perc = st.sidebar.number_input("Tasso risk-free annuo (%)", value=3.0, step=0.25, format="%.2f")
risk_free = rf_perc / 100.0
valuta_base = st.sidebar.selectbox("Valuta base", VALUTE_COMUNI, index=0)
converti = st.sidebar.checkbox(f"Converti tutto in {valuta_base}", value=True)

st.sidebar.divider()
if st.sidebar.button("🔄 Aggiorna dati (svuota cache)", width="stretch"):
    st.cache_data.clear()
    st.rerun()


# ---------------------------------------------------------------------------
# Intestazione
# ---------------------------------------------------------------------------

st.title("📊 Sharpe — Analisi ETF / Indici e Portafoglio")
st.caption(
    "⚠️ Strumento a scopo di **analisi e didattico**. Non costituisce "
    "consulenza finanziaria né raccomandazione di investimento. I dati "
    "provengono da Yahoo Finance e possono contenere errori o ritardi."
)


# ---------------------------------------------------------------------------
# Costruzione del portafoglio: ricerca + selezione
# ---------------------------------------------------------------------------

with st.container(border=True):
    st.markdown("### 🔎 Cerca e aggiungi ETF / indici")
    c1, c2 = st.columns([6, 1])
    c1.text_input(
        "Cerca",
        key="query",
        label_visibility="collapsed",
        placeholder="Cerca per nome o ticker (es. MSCI World, S&P 500, obbligazioni globali, SWDA)...",
    )
    c2.button("Cerca", on_click=cb_cerca, width="stretch")

    if ss.risultati:
        st.caption("Risultati — clicca «➕ Aggiungi» per inserire l'asset nel portafoglio:")
        for r in ss.risultati:
            rc1, rc2 = st.columns([6, 1])
            gia = r["symbol"] in ss.selezionati["Ticker"].values
            rc1.markdown(
                f"**{r['nome']}**  \n"
                f"`{r['symbol']}` · {r['tipo'] or 'n/d'} · {r['borsa'] or 'n/d'}"
            )
            rc2.button(
                "✓ inserito" if gia else "➕ Aggiungi",
                key=f"add_{r['symbol']}",
                disabled=gia,
                on_click=cb_aggiungi,
                args=(r["symbol"], r["nome"]),
                width="stretch",
            )

with st.container(border=True):
    st.markdown("### 📋 Portafoglio (asset selezionati e pesi)")

    sel = ss.selezionati.copy()
    sel["Ticker"] = sel["Ticker"].astype(str).str.strip().str.upper()
    sel = sel[sel["Ticker"] != ""].drop_duplicates(subset="Ticker").reset_index(drop=True)

    if sel.empty:
        st.info("Nessun asset selezionato. Usa la ricerca qui sopra per aggiungerne.")
        st.stop()

    # Intestazione delle colonne.
    h1, h2, h3 = st.columns([6, 2, 1])
    h1.markdown("**Asset**")
    h2.markdown("**Peso %**")
    h3.markdown("**Rimuovi**")

    pesi_correnti = {}
    for _, riga in sel.iterrows():
        t = riga["Ticker"]
        nome = riga["Nome"]
        # Inizializza lo stato del peso una sola volta (poi lo gestisce il widget).
        if f"w_{t}" not in ss:
            ss[f"w_{t}"] = float(riga["Peso %"]) if pd.notna(riga["Peso %"]) else 0.0
        col1, col2, col3 = st.columns([6, 2, 1])
        col1.markdown(f"**{nome}**  \n`{t}`")
        col2.number_input(
            "Peso %",
            min_value=0.0,
            step=1.0,
            key=f"w_{t}",
            label_visibility="collapsed",
        )
        col3.button("🗑", key=f"del_{t}", on_click=cb_rimuovi, args=(t,))
        pesi_correnti[t] = ss[f"w_{t}"]

    # Aggiorna i pesi memorizzati (utile per il salvataggio).
    ss.selezionati = sel.assign(**{"Peso %": [pesi_correnti[t] for t in sel["Ticker"]]})

    azione1, azione2, azione3 = st.columns([1, 1, 2])
    azione1.button("⚖️ Equipesati", on_click=cb_equipesati, width="stretch")
    azione2.button("🧹 Svuota", on_click=cb_svuota, width="stretch")
    tot = sum(pesi_correnti.values())
    azione3.metric("Somma pesi", f"{tot:.1f}%", help="I pesi vengono normalizzati a 100% per i calcoli.")

# Estrae ticker, pesi e nomi.
tickers = sel["Ticker"].tolist()
pesi_input = pd.Series([pesi_correnti[t] for t in tickers], index=tickers)


# ---------------------------------------------------------------------------
# Download dati
# ---------------------------------------------------------------------------

with st.spinner("Scarico i dati da Yahoo Finance..."):
    ris = carica_dati(
        tuple(tickers),
        period,
        pd.Timestamp(data_inizio) if data_inizio else None,
        pd.Timestamp(data_fine) if data_fine else None,
        valuta_base,
        converti,
    )

if ris.errori:
    for t, msg in ris.errori.items():
        st.warning(f"**{t}**: {msg}")

if ris.prezzi.empty:
    st.error("Nessun dato disponibile per gli asset indicati. Controlla i simboli e l'intervallo.")
    st.stop()

prezzi = ris.prezzi
tickers_ok = list(prezzi.columns)
pesi = mtr.normalizza_pesi(pesi_input, tickers_ok)
rendimenti = mtr.rendimenti_giornalieri(prezzi)

# Mappa ticker -> nome reale (per mostrare i nomi nelle analisi).
nomi = {t: ss.selezionati.set_index("Ticker")["Nome"].get(t, t) for t in tickers_ok}
nomi_corti = {t: etichetta_corta(nomi[t]) for t in tickers_ok}

# Riepilogo.
col1, col2, col3 = st.columns(3)
col1.metric("Asset analizzati", len(tickers_ok))
col2.metric("Periodo", f"{prezzi.index.min():%d/%m/%Y} → {prezzi.index.max():%d/%m/%Y}")
col3.metric("Valuta", valuta_base if converti else "nativa (mista)")
if ris.valute:
    valute_txt = ", ".join(f"{nomi.get(t, t)}: {c}" for t, c in ris.valute.items())
    st.caption(f"Valute native rilevate — {valute_txt}")


# ---------------------------------------------------------------------------
# Tab di analisi
# ---------------------------------------------------------------------------

tab_asset, tab_pf, tab_alloc, tab_opt = st.tabs(
    ["📈 Singoli asset", "💼 Portafoglio", "🌍 Allocazione", "🧮 Ottimizzazione"]
)

# === TAB 1 — SINGOLI ASSET ================================================
with tab_asset:
    st.subheader("Metriche per singolo asset")
    met_asset = mtr.metriche_asset(rendimenti, risk_free).rename(index=nomi)
    st.dataframe(formatta_metriche(met_asset), width="stretch")

    st.subheader("Andamento normalizzato (base 100)")
    cum = mtr.serie_cumulata(rendimenti, base=100.0).rename(columns=nomi_corti)
    fig = px.line(cum, labels={"value": "Indice (base 100)", "index": "Data", "variable": "Asset"})
    fig.update_layout(legend_title_text="Asset", hovermode="x unified")
    st.plotly_chart(fig, width="stretch")

    st.subheader("Drawdown")
    dd = pd.DataFrame({nomi_corti[t]: mtr.serie_drawdown(rendimenti[t]) for t in tickers_ok})
    fig_dd = px.area(dd, labels={"value": "Drawdown", "index": "Data", "variable": "Asset"})
    fig_dd.update_layout(legend_title_text="Asset", hovermode="x unified")
    fig_dd.update_yaxes(tickformat=".0%")
    st.plotly_chart(fig_dd, width="stretch")

# === TAB 2 — PORTAFOGLIO ==================================================
with tab_pf:
    st.subheader("Metriche del portafoglio")
    st.caption("Pesi normalizzati: " + ", ".join(f"{nomi[t]} {p:.1%}" for t, p in pesi.items()))
    met_pf = mtr.metriche_portafoglio(rendimenti, pesi, risk_free)

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Rend. annuo (CAGR)", f"{met_pf['Rend. annuo (CAGR)']:.2%}")
    c2.metric("Volatilità (covarianza)", f"{met_pf['Volatilità annua (covarianza)']:.2%}")
    c3.metric("Sharpe", f"{met_pf['Sharpe']:.2f}")
    c4.metric("Sortino", f"{met_pf['Sortino']:.2f}")
    c5, c6, c7 = st.columns(3)
    c5.metric("Max drawdown", f"{met_pf['Max drawdown']:.2%}")
    c6.metric("Rend. cumulato", f"{met_pf['Rend. cumulato']:.2%}")
    c7.metric("Volatilità (serie)", f"{met_pf['Volatilità annua (serie)']:.2%}")

    st.subheader("Portafoglio vs singoli asset (base 100)")
    serie_pf = mtr.serie_rendimenti_portafoglio(rendimenti, pesi)
    cum_all = mtr.serie_cumulata(rendimenti, base=100.0).rename(columns=nomi_corti)
    cum_all["PORTAFOGLIO"] = mtr.serie_cumulata(serie_pf, base=100.0)
    fig_cmp = px.line(cum_all, labels={"value": "Indice (base 100)", "index": "Data", "variable": "Serie"})
    fig_cmp.update_traces(line=dict(width=1.2))
    fig_cmp.update_traces(selector=dict(name="PORTAFOGLIO"), line=dict(width=3.5, color="black"))
    fig_cmp.update_layout(hovermode="x unified")
    st.plotly_chart(fig_cmp, width="stretch")

    col_a, col_b = st.columns(2)
    with col_a:
        st.subheader("Matrice di correlazione")
        corr = mtr.matrice_correlazione(rendimenti).rename(index=nomi_corti, columns=nomi_corti)
        fig_corr = px.imshow(
            corr, text_auto=".2f", color_continuous_scale="RdBu_r", zmin=-1, zmax=1, aspect="auto"
        )
        st.plotly_chart(fig_corr, width="stretch")
        st.caption(
            "Valori vicini a 1 = molto correlati (poca diversificazione); "
            "vicini a 0 o negativi = scorrelati (maggiore diversificazione)."
        )

    with col_b:
        st.subheader("Contributo al rischio")
        rc = mtr.contributo_rischio(rendimenti, pesi).rename(index=nomi)
        rc_plot = rc.reset_index().rename(columns={"index": "Asset"})
        rc_plot["Asset"] = rc_plot["Asset"].map(etichetta_corta)
        fig_rc = px.bar(
            rc_plot, x="Asset", y="Contributo %",
            text=rc_plot["Contributo %"].map(lambda v: f"{v:.1%}"),
        )
        fig_rc.update_yaxes(tickformat=".0%")
        fig_rc.update_layout(showlegend=False)
        st.plotly_chart(fig_rc, width="stretch")
        st.caption(
            "Quanto ciascun asset contribuisce alla volatilità totale. "
            "Confronta col peso: chi contribuisce meno del proprio peso diversifica."
        )
        st.dataframe(
            rc.style.format(
                {
                    "Peso": "{:.2%}",
                    "Contributo marginale": "{:.4f}",
                    "Contributo assoluto": "{:.4f}",
                    "Contributo %": "{:.2%}",
                }
            ),
            width="stretch",
        )

# === TAB 3 — ALLOCAZIONE ==================================================
with tab_alloc:
    st.subheader("Composizione per paese e settore")
    st.info(
        "La composizione (holdings) **non** si ricava dai prezzi. Si può "
        "provare a recuperare i settori da yfinance (spesso assenti per ETF "
        "UCITS europei) e/o inserirla a mano qui sotto o da CSV. "
        "Le righe sono identificate dal **ticker**."
    )

    cbtn1, cbtn2 = st.columns(2)
    with cbtn1:
        if st.button("🔄 Recupera settori da yfinance", width="stretch"):
            settori = carica_settori(tuple(tickers_ok))
            if not settori:
                st.warning("Nessun dato di settore disponibile per questi ticker.")
            for t, sw in settori.items():
                ss.composizione.setdefault(t, {"paese": {}, "settore": {}})
                ss.composizione[t]["settore"].update(sw)
            if settori:
                st.success(f"Settori recuperati per: {', '.join(nomi.get(t, t) for t in settori)}")

    with cbtn2:
        file_csv = st.file_uploader("Carica composizione (CSV)", type=["csv"], key="up_csv")
        if file_csv is not None:
            try:
                comp_csv = dati.carica_composizione_csv(file_csv.getvalue())
                for t, sez in comp_csv.items():
                    ss.composizione.setdefault(t, {"paese": {}, "settore": {}})
                    ss.composizione[t]["paese"].update(sez.get("paese", {}))
                    ss.composizione[t]["settore"].update(sez.get("settore", {}))
                st.success("Composizione caricata dal CSV.")
            except Exception as exc:
                st.error(f"CSV non valido: {exc}")

    st.markdown("**Modifica manuale della composizione** (pesi in frazione, es. 0.25 = 25%)")
    comp_df = comp_to_dataframe(ss.composizione)
    comp_edit = st.data_editor(
        comp_df,
        num_rows="dynamic",
        width="stretch",
        key="editor_comp",
        column_config={
            "Tipo": st.column_config.SelectboxColumn("Tipo", options=["paese", "settore"]),
            "Peso": st.column_config.NumberColumn("Peso", min_value=0.0, max_value=1.0, step=0.01),
        },
    )
    ss.composizione = dataframe_to_comp(comp_edit)

    csv_str = dati.composizione_in_csv(ss.composizione)
    st.download_button("⬇️ Scarica composizione (CSV)", data=csv_str, file_name="composizione.csv", mime="text/csv")

    st.divider()

    for tipo, titolo in (("paese", "Distribuzione per paese"), ("settore", "Distribuzione per settore")):
        st.subheader(titolo)
        serie, mancanti = mtr.aggrega_composizione(pesi, ss.composizione, tipo)
        if mancanti:
            st.warning(
                f"Composizione **{tipo}** non disponibile per: "
                f"{', '.join(nomi.get(t, t) for t in mancanti)}. "
                "Questi asset sono esclusi dall'aggregazione (inseriscili sopra per includerli)."
            )
        if serie.empty:
            st.caption(f"Nessuna composizione di tipo «{tipo}» disponibile.")
            continue
        cpie, cbar = st.columns(2)
        with cpie:
            fig_pie = px.pie(values=serie.values, names=serie.index, hole=0.35)
            fig_pie.update_traces(textposition="inside", textinfo="percent+label")
            st.plotly_chart(fig_pie, width="stretch")
        with cbar:
            df_bar = serie.reset_index()
            df_bar.columns = [tipo.capitalize(), "Peso"]
            fig_bar = px.bar(df_bar, x="Peso", y=tipo.capitalize(), orientation="h")
            fig_bar.update_xaxes(tickformat=".0%")
            fig_bar.update_layout(yaxis={"categoryorder": "total ascending"})
            st.plotly_chart(fig_bar, width="stretch")

# === TAB 4 — OTTIMIZZAZIONE (EXTRA) =======================================
with tab_opt:
    st.subheader("Ottimizzazione del portafoglio")
    if len(tickers_ok) < 2:
        st.info("Servono almeno 2 asset per l'ottimizzazione.")
    else:
        # Scelta dell'obiettivo di ottimizzazione.
        OBIETTIVI = {
            "Minima varianza (minimo rischio)": "min_var",
            "Massimo rendimento annuo": "max_ret",
            "Massimo indice di Sharpe (tangenza)": "max_sharpe",
        }
        col_ob, col_lo = st.columns([2, 1])
        scelta = col_ob.selectbox("Obiettivo", list(OBIETTIVI.keys()), index=0)
        obiettivo = OBIETTIVI[scelta]
        long_only = col_lo.checkbox("Solo posizioni long (pesi ≥ 0)", value=True)
        if not mtr.SCIPY_DISPONIBILE:
            st.caption("scipy non disponibile: si usano soluzioni analitiche (possono dare pesi negativi).")

        # Quota minima per asset, espressa come % della quota equipesata (1/N).
        # Regola: L = α·(1/N). Garantisce che ogni asset resti > 0 e si scala
        # automaticamente col numero di asset (sempre ammissibile).
        n_asset = len(tickers_ok)
        if long_only:
            alpha_perc = st.slider(
                "Quota minima per asset (% della quota equipesata)",
                min_value=0, max_value=100, value=25, step=5,
                help="0% = nessun vincolo (un asset può andare a 0). "
                     "100% = tutti equipesati. Es. 25% con N asset → minimo 25%·(1/N).",
            )
            frazione_minima = alpha_perc / 100.0
            quota_equa = 1.0 / n_asset
            soglia_assoluta = frazione_minima * quota_equa
            st.caption(
                f"Con {n_asset} asset la quota equipesata è {quota_equa:.1%}: "
                f"ogni asset peserà **almeno {soglia_assoluta:.1%}** "
                f"(e **al massimo {1 - (n_asset - 1) * soglia_assoluta:.1%}**)."
            )
        else:
            frazione_minima = 0.0
            st.caption("Quota minima per asset disattivata: si applica solo in modalità long-only.")

        # Calcolo dei pesi ottimali per l'obiettivo scelto.
        w_opt = mtr.pesi_ottimizzati(rendimenti, obiettivo, risk_free, long_only, frazione_minima)
        met_opt = mtr.metriche_portafoglio(rendimenti, w_opt, risk_free)

        if obiettivo == "max_ret" and long_only:
            if frazione_minima <= 0:
                st.warning(
                    "Con soli pesi long e nessuna quota minima, il **massimo rendimento** "
                    "concentra tutto sull'asset col rendimento storico più alto. Alza la "
                    "quota minima qui sopra per distribuirlo sugli altri asset."
                )
            else:
                st.info(
                    "Il **massimo rendimento** assegna la quota minima a ogni asset e il "
                    "resto all'asset col rendimento storico più alto. Ricorda: massimizza "
                    "il rendimento passato, non riduce il rischio né garantisce il futuro."
                )

        col_pesi, col_conf = st.columns([1, 1])
        with col_pesi:
            st.markdown("**Pesi ottimali**")
            df_opt = w_opt.rename(index=nomi).to_frame("Peso ottimale")
            st.dataframe(df_opt.style.format({"Peso ottimale": "{:.2%}"}), width="stretch")
            st.button(
                "📌 Applica questi pesi al portafoglio",
                on_click=cb_applica_pesi,
                args=(dict(w_opt),),
                width="stretch",
                help="Sostituisce i pesi attuali con quelli ottimali (poi rivedi le altre tab).",
            )

        with col_conf:
            st.markdown("**Confronto: portafoglio attuale vs ottimale**")
            confronto = pd.DataFrame(
                {
                    "Attuale": [
                        met_pf["Rend. annuo (CAGR)"],
                        met_pf["Volatilità annua (covarianza)"],
                        met_pf["Sharpe"],
                        met_pf["Sortino"],
                        met_pf["Max drawdown"],
                    ],
                    "Ottimale": [
                        met_opt["Rend. annuo (CAGR)"],
                        met_opt["Volatilità annua (covarianza)"],
                        met_opt["Sharpe"],
                        met_opt["Sortino"],
                        met_opt["Max drawdown"],
                    ],
                },
                index=["Rend. annuo", "Volatilità", "Sharpe", "Sortino", "Max drawdown"],
            )
            st.dataframe(
                confronto.style.format(
                    {"Attuale": "{:.2%}", "Ottimale": "{:.2%}"},
                    subset=pd.IndexSlice[["Rend. annuo", "Volatilità", "Max drawdown"], :],
                ).format(
                    {"Attuale": "{:.2f}", "Ottimale": "{:.2f}"},
                    subset=pd.IndexSlice[["Sharpe", "Sortino"], :],
                ),
                width="stretch",
            )

        st.subheader("Frontiera efficiente")
        if mtr.SCIPY_DISPONIBILE:
            front = mtr.frontiera_efficiente(rendimenti, n_punti=40, long_only=long_only, frazione_minima=frazione_minima)
            if not front.empty:
                fig_f = go.Figure()
                fig_f.add_trace(go.Scatter(x=front["vol"], y=front["rend"], mode="lines", name="Frontiera"))
                mu_asset = rendimenti.mean() * mtr.GIORNI_BORSA
                vol_asset = rendimenti.std(ddof=1) * (mtr.GIORNI_BORSA ** 0.5)
                fig_f.add_trace(
                    go.Scatter(
                        x=vol_asset.values, y=mu_asset.values, mode="markers+text",
                        text=[nomi_corti[t] for t in rendimenti.columns],
                        textposition="top center", name="Asset",
                    )
                )
                fig_f.add_trace(
                    go.Scatter(
                        x=[met_pf["Volatilità annua (covarianza)"]],
                        y=[met_pf["Rend. annuo (CAGR)"]],
                        mode="markers", marker=dict(size=13, symbol="diamond", color="gray"),
                        name="Portafoglio attuale",
                    )
                )
                # Punto del portafoglio ottimale (obiettivo selezionato).
                fig_f.add_trace(
                    go.Scatter(
                        x=[met_opt["Volatilità annua (covarianza)"]],
                        y=[met_opt["Rend. annuo (CAGR)"]],
                        mode="markers", marker=dict(size=16, symbol="star", color="green"),
                        name=f"Ottimale ({scelta.split('(')[0].strip()})",
                    )
                )
                fig_f.update_layout(xaxis_title="Volatilità annua", yaxis_title="Rendimento medio annuo", hovermode="closest")
                fig_f.update_xaxes(tickformat=".0%")
                fig_f.update_yaxes(tickformat=".0%")
                st.plotly_chart(fig_f, width="stretch")
            else:
                st.caption("Impossibile calcolare la frontiera per questo insieme di asset.")
        else:
            st.caption("Installa scipy per visualizzare la frontiera efficiente.")


# ---------------------------------------------------------------------------
# Sidebar: salvataggio portafoglio
# ---------------------------------------------------------------------------

st.sidebar.divider()
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
