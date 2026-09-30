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

st.set_page_config(
    page_title="Sharpe — Analisi ETF & Portafoglio",
    layout="wide",
    initial_sidebar_state="auto",  # su schermi piccoli la barra laterale si chiude da sola
)

# Stato condiviso (portafoglio di esempio, composizione) e parametri comuni.
cm.init_state()

# CSS responsive: migliora la resa su smartphone senza toccare il desktop.
cm.inietta_css_mobile()

st.title("📊 Sharpe")
st.caption(
    "Analizza **ETF e indici**, costruisci un **portafoglio** e studia rischio, rendimento e "
    "diversificazione — semplice, in italiano e **didattico**."
)

# «Cos'è e come si usa» in un solo riquadro, aperto solo alla prima visita (utile a nuovi
# utenti, AI e indicizzazione Google). Il disclaimer completo è nel footer di ogni pagina.
cm.mostra_intro()

avanzato = st.session_state.get("modo_ui_val", "Base") == "Avanzato"

# Indicatore GENERALE di mercato (risk-on / risk-off): strumento di market timing,
# quindi solo in modalità «Avanzato» (in Base resta il messaggio «resta investito»).
if avanzato:
    cm.mostra_semaforo_mercato()

cm.sidebar_parametri()

# Navigazione tra le sezioni. L'Analisi tecnica (strumento avanzato) compare solo in
# modalità «Avanzato» (punto 4: coerenza con l'investitore passivo).
pagine = [st.Page("page_builder.py", title="Builder — Portafoglio", icon="🧱", default=True)]
if avanzato:
    pagine.append(st.Page("page_analisi.py", title="Analisi tecnica", icon="📈"))
st.navigation(pagine).run()
