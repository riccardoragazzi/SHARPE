"""
page_analisi.py
===============
Pagina "Analisi tecnica": per un singolo asset del portafoglio mostra il
grafico a candele con medie mobili, i volumi e l'RSI, con strumenti per
disegnare linee/trendline e un selettore di intervallo (YTD / 1A / 3A / 5A /
10A / max). In più, le statistiche principali calcolate sull'intervallo scelto.

I prezzi sono quelli **nativi** dell'asset (non convertiti), come d'uso per
l'analisi tecnica.
"""

from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from plotly.subplots import make_subplots

import common as cm
import dataset_composizioni as dsc
import metrics as mtr

ss = st.session_state

st.header("📈 Analisi tecnica per asset")
st.caption(
    "ℹ️ Strumento **educativo** di analisi tecnica. Per un investitore di lungo periodo conta soprattutto "
    "**restare investiti**: il *market timing* (provare a entrare/uscire al momento giusto) è molto "
    "difficile e spesso controproducente."
)


def _cerca_analisi():
    """Ricerca un asset qualsiasi (per la pagina Analisi)."""
    ss.risultati_analisi = cm.cerca(ss.get("query_analisi", ""))


def _scegli_analisi(symbol, nome):
    """Imposta l'asset cercato come asset da analizzare."""
    ss.analisi_ticker = symbol
    ss.analisi_nome = nome


# ---------------------------------------------------------------------------
# Scelta dell'asset: dal portafoglio oppure cercandone uno qualsiasi
# ---------------------------------------------------------------------------

sel = cm.portafoglio_pulito()
modo = st.radio(
    "Asset da analizzare", ["Da portafoglio", "Cerca un asset"], horizontal=True,
    help="«Da portafoglio»: scegli tra gli asset che hai inserito. «Cerca un asset»: "
         "analizza QUALSIASI ETF/indice/azione, anche se non è nel tuo portafoglio.",
)

ticker, nome_asset = None, None
if modo == "Da portafoglio":
    if sel.empty:
        st.info("Nessun asset nel portafoglio. Usa **«Cerca un asset»** qui sopra, "
                "oppure aggiungine nel **Builder**.")
        st.stop()
    nomi_pf = dict(zip(sel["Ticker"], sel["Nome"]))
    ticker = st.selectbox("Asset", options=sel["Ticker"].tolist(),
                          format_func=lambda t: f"{nomi_pf.get(t, t)}  ({t})")
    nome_asset = nomi_pf.get(ticker, ticker)
else:
    cca, ccb = st.columns([6, 1])
    cca.text_input(
        "Cerca asset", key="query_analisi", label_visibility="collapsed",
        placeholder="Cerca per nome, ticker o ISIN (es. MSCI World, AAPL, IE00B4L5Y983)...",
    )
    ccb.button("Cerca", key="btn_cerca_analisi", on_click=_cerca_analisi, width="stretch")
    if ss.get("risultati_analisi"):
        st.caption("Risultati — «📈 Analizza» per vederne l'analisi, «➕» per aggiungerlo al portafoglio:")
        for r in ss.risultati_analisi:
            rc1, rc2, rc3 = st.columns([5, 1, 1])
            _iz = dsc.isin_di(r["symbol"])
            rc1.markdown(
                f"**{r['nome']}**  \n`{r['symbol']}` · {r['tipo'] or 'n/d'} · {r['borsa'] or 'n/d'}"
                + (f" · ISIN `{_iz}`" if _iz else "")
            )
            rc2.button("📈 Analizza", key=f"an_{r['symbol']}", on_click=_scegli_analisi,
                       args=(r["symbol"], r["nome"]), width="stretch")
            gia = r["symbol"] in ss.selezionati["Ticker"].values
            rc3.button("✓" if gia else "➕", key=f"addan_{r['symbol']}", disabled=gia,
                       on_click=cm.cb_aggiungi, args=(r["symbol"], r["nome"]), width="stretch",
                       help="Aggiungi questo asset al portafoglio")
    ticker = ss.get("analisi_ticker")
    nome_asset = ss.get("analisi_nome") or ticker
    if not ticker:
        st.info("Cerca un asset qui sopra e premi **📈 Analizza** per vederne l'analisi completa.")
        st.stop()
    st.success(f"Asset in analisi: **{nome_asset}**  (`{ticker}`)")

# ---------------------------------------------------------------------------
# Controlli: intervallo, indicatori
# ---------------------------------------------------------------------------

intervallo = st.radio(
    "Intervallo", ["YTD", "1A", "3A", "5A", "10A", "max"], index=3, horizontal=True,
    help="Quanto storico mostrare nel grafico. YTD = da inizio anno; max = tutto lo storico.",
)


def _parse_periodi(testo: str) -> list[int]:
    """Estrae una lista di periodi (interi) da un testo tipo '20, 50, 200'."""
    periodi = []
    for pezzo in testo.replace(";", ",").split(","):
        pezzo = pezzo.strip()
        if pezzo.isdigit():
            v = int(pezzo)
            if 1 <= v <= 1000:
                periodi.append(v)
    return sorted(set(periodi))


with st.expander("⚙️ Indicatori da mostrare", expanded=True):
    cc1, cc2 = st.columns(2)
    with cc1:
        tipo_media = st.radio("Tipo di media mobile", ["SMA", "EMA"], horizontal=True)
        testo_periodi = st.text_input(
            "Periodi medie mobili (giorni, separati da virgola)", value="50, 200",
            help="Scrivi i periodi che vuoi, es. 20, 50, 100, 200. Lascia vuoto per non mostrarne.",
        )
        medie = _parse_periodi(testo_periodi)
    with cc2:
        mostra_volume = st.checkbox("Mostra volumi", value=True)
        mostra_rsi = st.checkbox("Mostra RSI", value=True)
        periodo_rsi = st.number_input("Periodo RSI", min_value=2, max_value=100, value=14, step=1, disabled=not mostra_rsi)

# ---------------------------------------------------------------------------
# Dati OHLCV (tutto lo storico) + indicatori, poi ritaglio sull'intervallo
# ---------------------------------------------------------------------------

with st.spinner("Scarico i dati..."):
    full = cm.ohlcv(ticker, period="max")

if full.empty or "Close" not in full.columns:
    st.error(f"Dati non disponibili per **{nome_asset}** ({ticker}).")
    st.stop()

cm.mostra_avvisi_qualita(full[["Close"]])
st.caption(f"📅 Dati aggiornati al **{full.index.max():%d/%m/%Y}** (fonte: Yahoo Finance).")

close_full = full["Close"]
# Gli indicatori si calcolano sull'intero storico, così sono corretti anche
# al bordo sinistro della finestra visualizzata.
if tipo_media == "EMA":
    ma_full = {p: mtr.media_mobile_esp(close_full, p) for p in medie}
else:
    ma_full = {p: mtr.media_mobile(close_full, p) for p in medie}
rsi_full = mtr.rsi(close_full, int(periodo_rsi))


def _data_taglio(intervallo: str, ultima: pd.Timestamp):
    """Data di inizio dell'intervallo selezionato (None = tutto)."""
    if intervallo == "max":
        return None
    if intervallo == "YTD":
        return pd.Timestamp(year=ultima.year, month=1, day=1)
    anni = {"1A": 1, "3A": 3, "5A": 5, "10A": 10}[intervallo]
    return ultima - pd.DateOffset(years=anni)


ultima = full.index.max()
taglio = _data_taglio(intervallo, ultima)
maschera = full.index >= taglio if taglio is not None else full.index == full.index
df = full.loc[maschera]

if df.empty:
    st.warning("Nessun dato nell'intervallo selezionato.")
    st.stop()

# ---------------------------------------------------------------------------
# Statistiche principali sull'intervallo
# ---------------------------------------------------------------------------

rend = df["Close"].pct_change().dropna()
risk_free = ss.risk_free
st.subheader(f"Statistiche · {nome_asset} · {intervallo}")
m1, m2, m3, m4, m5, m6 = st.columns(6)
m1.metric("Rend. cumulato", f"{cm.fmt_pct(mtr.rendimento_cumulato(rend))}")
m2.metric("Rend. annuo (CAGR)", f"{cm.fmt_pct(mtr.cagr(rend))}")
m3.metric("Volatilità", f"{cm.fmt_pct(mtr.volatilita_annua(rend))}")
m4.metric("Sharpe", f"{cm.fmt_num(mtr.sharpe(rend, risk_free), 2)}")
m5.metric("Sortino", f"{cm.fmt_num(mtr.sortino(rend, risk_free), 2)}")
m6.metric("Max drawdown", f"{cm.fmt_pct(mtr.max_drawdown(rend))}")
st.caption(
    f"Ultimo prezzo: **{cm.fmt_num(df['Close'].iloc[-1], 2)}** (valuta nativa) · "
    f"periodo {df.index.min():%d/%m/%Y} → {df.index.max():%d/%m/%Y} · "
    f"{len(df)} sedute. Prezzi aggiustati per dividendi/split."
)

# ---------------------------------------------------------------------------
# Grafico a candele + medie mobili + volumi + RSI
# ---------------------------------------------------------------------------

# Composizione delle righe del grafico in base agli indicatori scelti.
righe = 1 + (1 if mostra_volume else 0) + (1 if mostra_rsi else 0)
if mostra_volume and mostra_rsi:
    altezze = [0.6, 0.2, 0.2]
elif mostra_volume or mostra_rsi:
    altezze = [0.74, 0.26]
else:
    altezze = [1.0]

fig = make_subplots(
    rows=righe, cols=1, shared_xaxes=True, vertical_spacing=0.03, row_heights=altezze
)

# Candele (riga 1).
fig.add_trace(
    go.Candlestick(
        x=df.index, open=df["Open"], high=df["High"], low=df["Low"], close=df["Close"],
        name="Prezzo", increasing_line_color="#26a69a", decreasing_line_color="#ef5350",
    ),
    row=1, col=1,
)
# Medie mobili sovrapposte al prezzo.
for p in medie:
    fig.add_trace(
        go.Scatter(x=df.index, y=ma_full[p].loc[df.index], mode="lines", name=f"{tipo_media} {p}", line=dict(width=1.3)),
        row=1, col=1,
    )

riga_corrente = 1
if mostra_volume and "Volume" in df.columns:
    riga_corrente += 1
    colori = ["#26a69a" if c >= o else "#ef5350" for o, c in zip(df["Open"], df["Close"])]
    fig.add_trace(
        go.Bar(x=df.index, y=df["Volume"], name="Volume", marker_color=colori, showlegend=False),
        row=riga_corrente, col=1,
    )
    fig.update_yaxes(title_text="Volume", row=riga_corrente, col=1)

if mostra_rsi:
    riga_corrente += 1
    rsi_s = rsi_full.loc[df.index]
    fig.add_trace(go.Scatter(x=df.index, y=rsi_s, mode="lines", name=f"RSI({int(periodo_rsi)})", line=dict(color="#7e57c2")), row=riga_corrente, col=1)
    # Soglie 70 (ipercomprato) e 30 (ipervenduto).
    fig.add_hline(y=70, line_dash="dash", line_color="red", opacity=0.5, row=riga_corrente, col=1)
    fig.add_hline(y=30, line_dash="dash", line_color="green", opacity=0.5, row=riga_corrente, col=1)
    fig.update_yaxes(title_text="RSI", range=[0, 100], row=riga_corrente, col=1)

fig.update_layout(
    height=720,
    xaxis_rangeslider_visible=False,
    hovermode="x unified",
    legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="left", x=0),
    margin=dict(t=30, b=20),
    # Strumenti di disegno per l'analisi tecnica.
    dragmode="drawline",
    newshape=dict(line_color="#00BFFF", line_width=2),
)

config = {
    "scrollZoom": True,
    "modeBarButtonsToAdd": ["drawline", "drawopenpath", "drawrect", "drawcircle", "eraseshape"],
    "displaylogo": False,
}

st.plotly_chart(fig, width="stretch", config=config)
st.caption(
    "Cosa significa per te: ogni candela è una giornata (verde = chiusura sopra l'apertura, rossa = "
    "sotto); le **medie mobili** mostrano la tendenza di fondo e l'**RSI** se l'asset è 'tirato'. Sono "
    "strumenti da analisi tecnica: utili da capire, ma non indispensabili per un investitore passivo."
)
st.caption(
    "✏️ Per disegnare: scegli uno strumento (linea, tratto libero, rettangolo) dalla barra in alto a "
    "destra del grafico, poi traccia sul grafico. La gomma cancella. ⚠️ I disegni **non** restano salvati "
    "al ricaricamento della pagina."
)

st.divider()
st.subheader("📊 Lettura statistica dell'asset")
st.caption(
    "«Prezzo vs media» e RSI sono calcolati su **tutto lo storico**; il «vantaggio statistico» "
    "sull'**intervallo selezionato**. (Il semaforo risk-on/off generale è in cima all'app.)"
)
cm.mostra_lettura_statistica(close_full, rend, risk_free, chiave=f"asset_{ticker}")

cm.mostra_glossario()

# A3 — footer disclaimer persistente.
cm.mostra_footer_disclaimer()
