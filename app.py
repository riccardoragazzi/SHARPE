"""
app.py
======
Punto d'ingresso dell'app Sharpe. Configura la pagina, lo stato condiviso e la
barra laterale dei parametri, poi gestisce la navigazione tra le due sezioni:

- 🧱 **Builder** ([page_builder.py]) — costruzione e analisi del portafoglio
- 📈 **Analisi tecnica** ([page_analisi.py]) — candele, volumi, medie mobili, RSI

Avvio:
    streamlit run app.py     (oppure: python -m streamlit run app.py)

Strumento a scopo di analisi / didattico: NON costituisce consulenza finanziaria.
"""

from __future__ import annotations

import streamlit as st

import common as cm

st.set_page_config(page_title="Sharpe — Analisi ETF & Portafoglio", layout="wide")

# Stato condiviso (portafoglio di esempio, composizione) e parametri comuni.
cm.init_state()

st.title("📊 Sharpe — Analisi ETF / Indici e Portafoglio")
st.caption(
    "⚠️ Strumento a scopo di **analisi e didattico**. Non costituisce consulenza "
    "finanziaria né raccomandazione di investimento. I dati provengono da Yahoo "
    "Finance e possono contenere errori o ritardi."
)

cm.sidebar_parametri()

# Navigazione tra le due sezioni.
pagine = [
    st.Page("page_builder.py", title="Builder — Portafoglio", icon="🧱", default=True),
    st.Page("page_analisi.py", title="Analisi tecnica", icon="📈"),
]
st.navigation(pagine).run()
