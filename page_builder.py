"""
page_builder.py
===============
Pagina "Builder": costruzione del portafoglio (ricerca, selezione, pesi) e
analisi di portafoglio (metriche, confronto, correlazioni, contributo al
rischio, allocazione, ottimizzazione).
"""

from __future__ import annotations

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

import common as cm
import data as dati
import dataset_composizioni as dsc
import metrics as mtr

ss = st.session_state

st.header("🧱 Builder")
st.caption("Costruzione e analisi del portafoglio.")

# ---------------------------------------------------------------------------
# Ricerca e selezione asset
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
    c2.button("Cerca", on_click=cm.cb_cerca, width="stretch")

    if ss.risultati:
        st.caption("Risultati — clicca «➕ Aggiungi» per inserire l'asset nel portafoglio:")
        for r in ss.risultati:
            rc1, rc2 = st.columns([6, 1])
            gia = r["symbol"] in ss.selezionati["Ticker"].values
            _iz = dsc.isin_di(r["symbol"])
            rc1.markdown(
                f"**{r['nome']}**  \n`{r['symbol']}` · {r['tipo'] or 'n/d'} · {r['borsa'] or 'n/d'}"
                + (f" · ISIN `{_iz}`" if _iz else "")
            )
            rc2.button(
                "✓ inserito" if gia else "➕ Aggiungi",
                key=f"add_{r['symbol']}",
                disabled=gia,
                on_click=cm.cb_aggiungi,
                args=(r["symbol"], r["nome"]),
                width="stretch",
            )

with st.container(border=True):
    st.markdown("### 📋 Portafoglio (asset selezionati e pesi)")

    # B4 — portafogli pronti "in evidenza" come pulsanti cliccabili (un clic per partire).
    st.caption("🚀 Parti da un portafoglio pronto (passivo e diversificato):")
    _pc = st.columns(len(cm.PRESET_IN_EVIDENZA))
    for _i, _nome in enumerate(cm.PRESET_IN_EVIDENZA):
        _pc[_i].button(_nome, key=f"preset_ev_{_i}", width="stretch",
                       on_click=cm.cb_carica_preset, args=(_nome,))

    # Portafogli "pronti" da caricare con un clic (lista completa).
    pp1, pp2 = st.columns([3, 1])
    preset_sel = pp1.selectbox(
        "Portafogli pronti", ["—"] + list(cm.PORTAFOGLI_PRONTI.keys()),
        help="Carica un portafoglio già pronto e diversificato (sostituisce gli asset attuali).",
    )
    pp2.button("📥 Carica preset", on_click=cm.cb_carica_preset, args=(preset_sel,),
               disabled=(preset_sel == "—"), width="stretch")

    sel = cm.portafoglio_pulito()
    if sel.empty:
        st.info("Nessun asset selezionato. Usa la ricerca qui sopra, oppure carica un **portafoglio pronto**.")
        st.stop()

    h1, h2, h3 = st.columns([5, 4, 1])
    h1.markdown("**Asset**")
    h2.markdown("**Peso %**")
    h3.markdown("**Rimuovi**")

    pesi_correnti = {}
    for _, riga in sel.iterrows():
        t = riga["Ticker"]
        nome = riga["Nome"]
        if f"w_{t}" not in ss:
            ss[f"w_{t}"] = round(float(riga["Peso %"]), 2) if pd.notna(riga["Peso %"]) else 0.0
        col1, col2, col3 = st.columns([5, 4, 1])
        _iz = cm.isin_di(t)
        col1.markdown(f"**{nome}**  \n`{t}`" + (f" · ISIN `{_iz}`" if _iz else ""))
        col2.slider("Peso %", min_value=0.0, max_value=100.0, step=1.0, key=f"w_{t}", label_visibility="collapsed")
        col3.button("🗑", key=f"del_{t}", on_click=cm.cb_rimuovi, args=(t,))
        pesi_correnti[t] = ss[f"w_{t}"]

    ss.selezionati = sel.assign(**{"Peso %": [pesi_correnti[t] for t in sel["Ticker"]]})

    azione1, azione2, azione3, azione4 = st.columns([1, 1, 1, 1])
    azione1.button("⚖️ Equipesati", on_click=cm.cb_equipesati, width="stretch")
    azione2.button("🎯 Normalizza a 100%", on_click=cm.cb_normalizza, width="stretch",
                   help="Riscala i pesi così che sommino esattamente a 100%.")
    azione3.button("🧹 Svuota", on_click=cm.cb_svuota, width="stretch")
    tot = sum(pesi_correnti.values())
    azione4.metric("Somma pesi", f"{tot:.1f}%", help="I pesi vengono comunque normalizzati a 100% per i calcoli.")

tickers = sel["Ticker"].tolist()
pesi_input = pd.Series([pesi_correnti[t] for t in tickers], index=tickers)

# ---------------------------------------------------------------------------
# Download dati e calcoli
# ---------------------------------------------------------------------------

with st.spinner("⏳ Sto scaricando i dati di mercato dei tuoi ETF da Yahoo Finance… "
                "al primo avvio può richiedere qualche secondo."):
    ris = cm.carica_dati(
        tuple(tickers), ss.period, ss.data_inizio, ss.data_fine, ss.valuta_base, ss.converti
    )

if ris.errori:
    for t, msg in ris.errori.items():
        st.warning(f"**{t}**: {msg}")

if ris.prezzi.empty:
    st.error("Nessun dato disponibile per il **periodo comune** a tutti gli asset selezionati.")
    nome_di = ss.selezionati.set_index("Ticker")["Nome"].to_dict()
    diag = mtr.diagnostica_periodo_comune(ris.finestre)
    if diag.get("valido"):
        if not diag["sovrapposizione"]:
            ci, cf = diag["colpevole_inizio"], diag["colpevole_fine"]
            st.warning(
                "❌ Gli asset **non hanno un periodo storico in comune**. "
                f"**{nome_di.get(ci, ci)}** (`{ci}`) ha dati che iniziano solo il "
                f"**{diag['inizio_comune']:%d/%m/%Y}**, ma **{nome_di.get(cf, cf)}** (`{cf}`) "
                f"finisce già il **{diag['fine_comune']:%d/%m/%Y}**: non c'è sovrapposizione. "
                "Prova a **rimuovere uno dei due** (spesso il colpevole è un ETF di nicchia con "
                "storico scarso o non aggiornato su Yahoo)."
            )
        else:
            st.warning(
                "Gli asset si sovrappongono nel tempo, ma dopo l'allineamento non resta nulla: può "
                f"dipendere dalla **conversione valuta** o da uno storico molto corto. Prova a "
                f"disattivare «Converti tutto in {ss.valuta_base}» nella barra laterale, oppure ad "
                "accorciare il periodo."
            )
        righe_fin = [
            {"Asset": nome_di.get(t, t), "Ticker": t,
             "Inizio": f"{p:%d/%m/%Y}", "Fine": f"{u:%d/%m/%Y}", "Giorni": n}
            for t, p, u, n in diag["voci"]
        ]
        st.markdown("**Storico disponibile su Yahoo per ciascun asset** (ordinato per data d'inizio):")
        st.dataframe(pd.DataFrame(righe_fin), width="stretch", hide_index=True)
    st.caption(
        "💡 Consigli: aggiungi gli asset **pochi alla volta** per scoprire il colpevole; per gli ETF "
        "di nicchia prova il simbolo **.MI** (Milano), **.L** (Londra) o cerca per **ISIN**; in barra "
        "laterale puoi **accorciare il periodo**."
    )
    st.stop()

prezzi = ris.prezzi
tickers_ok = list(prezzi.columns)
pesi = mtr.normalizza_pesi(pesi_input, tickers_ok)
rendimenti = mtr.rendimenti_giornalieri(prezzi)
risk_free = ss.risk_free

nomi = {t: ss.selezionati.set_index("Ticker")["Nome"].get(t, t) for t in tickers_ok}
nomi_corti = {t: cm.etichetta_corta(nomi[t]) for t in tickers_ok}

# Metriche del portafoglio: calcolate qui (una volta) perché servono sia alla
# sezione «Portafoglio» sia alla sezione «Ottimizzazione». Con il menu a tendina
# viene eseguita una sola sezione per volta, quindi met_pf deve essere già pronto.
met_pf = mtr.metriche_portafoglio(rendimenti, pesi, risk_free)

col1, col2, col3 = st.columns(3)
col1.metric("Asset analizzati", len(tickers_ok))
col2.metric("Periodo", f"{prezzi.index.min():%d/%m/%Y} → {prezzi.index.max():%d/%m/%Y}")
col3.metric("Valuta", ss.valuta_base if ss.converti else "nativa (mista)")

# A2 — freschezza: data dell'ultima quotazione disponibile.
st.caption(f"📅 Dati aggiornati al **{prezzi.index.max():%d/%m/%Y}** (fonte: Yahoo Finance).")

# A1 — chiarisce che è la valuta di QUOTAZIONE (borsa), non quella del sottostante.
if ris.valute:
    valute_txt = ", ".join(f"{nomi.get(t, t)}: {c}" for t, c in ris.valute.items())
    st.caption(f"Valuta di **quotazione** (borsa) rilevata — {valute_txt}. _Non è la valuta del sottostante._")
cm.mostra_box_rischio_cambio()

# A4 — se un asset accorcia la finestra comune, dillo esplicitamente.
_diag = mtr.diagnostica_periodo_comune(ris.finestre)
if _diag.get("valido") and len(tickers_ok) > 1:
    _inizio_piu_vecchio = min(p for _t, p, _u, _n in _diag["voci"])
    if _diag["inizio_comune"] > _inizio_piu_vecchio:
        _colp = _diag["colpevole_inizio"]
        st.caption(
            f"ℹ️ Periodo comune **dal {_diag['inizio_comune']:%d/%m/%Y}**, limitato da "
            f"**{nomi.get(_colp, _colp)}** (l'asset con lo storico più corto)."
        )

with st.expander("📅 Storico disponibile per asset (e periodo comune usato)"):
    if _diag.get("valido"):
        _righe = [
            {"Asset": nomi.get(t, t), "Ticker": t,
             "Inizio": f"{p:%d/%m/%Y}", "Fine": f"{u:%d/%m/%Y}", "Giorni": n}
            for t, p, u, n in _diag["voci"]
        ]
        st.dataframe(pd.DataFrame(_righe), width="stretch", hide_index=True)
    st.caption(
        "Il portafoglio usa il **periodo comune a tutti** gli asset: quello con lo storico più corto "
        "(o che parte più tardi) limita il periodo analizzato per gli altri."
    )

# Avvisi sulla qualità dei dati (storico corto, buchi, anomalie).
cm.mostra_avvisi_qualita(prezzi)

# ---------------------------------------------------------------------------
# Riepilogo automatico (in italiano semplice)
# ---------------------------------------------------------------------------

orizzonte = int(ss.get("orizzonte", 10))
riep = mtr.riepilogo_portafoglio(rendimenti, pesi, orizzonte, risk_free)
_box = {"success": st.success, "warning": st.warning}.get(riep["livello"], st.info)
_box("🧭 " + riep["testo"])
with st.expander("Come leggo questo riepilogo?"):
    st.markdown(
        "- **Diversificazione**: quanto i tuoi asset sono diversi tra loro (più alta = meno "
        "dipendi da un singolo mercato). Tiene conto di numero di asset, correlazione media e "
        "concentrazione del rischio.\n"
        "- **Rischio**: basato sulla **volatilità annua** (quanto oscilla il valore): "
        "sotto 8% basso, 8–15% medio, oltre 15% alto.\n"
        "- **Orizzonte**: impostalo nella barra laterale; più è lungo, più puoi assorbire le "
        "oscillazioni di breve periodo.\n\n"
        "_È una descrizione statistica/didattica, non un consiglio di investimento._"
    )

cm.mostra_glossario()

# ---------------------------------------------------------------------------
# Tab di analisi del portafoglio
# ---------------------------------------------------------------------------

SEZIONI = [
    "📋 Report", "📈 Singoli asset", "💼 Portafoglio", "🌍 Allocazione", "⏱️ Timing", "💶 PAC",
    "🎯 Obiettivo", "💰 Costi e tasse", "💸 Dividendi", "♻️ Ribilanciamento", "📊 Statistica",
    "🧮 Ottimizzazione", "🆚 Confronto", "🤖 Assistente",
]
# B1 — Modalità Base/Avanzato: in Base mostra solo l'essenziale per un passivo.
SEZIONI_BASE = ["📋 Report", "📈 Singoli asset", "💼 Portafoglio", "🌍 Allocazione",
                "💶 PAC", "🎯 Obiettivo", "🤖 Assistente"]
modo_ui = st.radio(
    "Modalità", ["Base", "Avanzato"], horizontal=True, key="modo_ui",
    help="Base = l'essenziale per un investitore passivo. Avanzato = tutte le sezioni.",
)
opzioni_sez = SEZIONI_BASE if modo_ui == "Base" else SEZIONI
# Se la sezione salvata non è tra le opzioni correnti, riparti dalla prima.
if ss.get("sezione_builder") not in opzioni_sez:
    ss["sezione_builder"] = opzioni_sez[0]
sezione = st.selectbox(
    "📂 Sezione da visualizzare",
    opzioni_sez,
    key="sezione_builder",
    help="Scegli cosa analizzare. Su telefono è più comodo di tante schede affiancate; "
         "inoltre viene calcolata solo la sezione scelta, quindi è più veloce.",
)

# === Report (vista di sintesi unica) =======================================
if sezione == "📋 Report":
    st.subheader("📋 Report del portafoglio")
    _box_r = {"success": st.success, "warning": st.warning}.get(riep["livello"], st.info)
    _box_r("🧭 " + riep["testo"])

    r1, r2, r3 = st.columns(3)
    r1.metric("Rend. annuo (CAGR)", cm.fmt_pct(met_pf['Rend. annuo (CAGR)']))
    r2.metric("Volatilità annua", cm.fmt_pct(met_pf['Volatilità annua (covarianza)']))
    r3.metric("Sharpe", cm.fmt_num(met_pf['Sharpe']))
    r4, r5, r6 = st.columns(3)
    r4.metric("Sortino", cm.fmt_num(met_pf['Sortino']))
    r5.metric("Max drawdown", cm.fmt_pct(met_pf['Max drawdown']))
    r6.metric("Rend. cumulato", cm.fmt_pct(met_pf['Rend. cumulato']))

    _infl_r = ss.get("inflazione", 0.0)
    if _infl_r > 0 and not pd.isna(met_pf["Rend. annuo (CAGR)"]):
        _cagr_reale = (1 + met_pf["Rend. annuo (CAGR)"]) / (1 + _infl_r) - 1
        st.caption(
            f"Al netto di un'inflazione del {cm.fmt_pct(_infl_r, 1)}/anno, il rendimento **reale** "
            f"(potere d'acquisto) è **{cm.fmt_pct(_cagr_reale)}/anno**."
        )

    # Andamento del portafoglio vs benchmark (base 100).
    st.markdown("**Andamento: il tuo portafoglio vs benchmark** (base 100)")
    serie_pf_r = mtr.serie_rendimenti_portafoglio(rendimenti, pesi)
    dati_cum = {"Il mio portafoglio": mtr.serie_cumulata(serie_pf_r, base=100.0)}
    with st.spinner("Carico i benchmark di confronto..."):
        for _bench in ("100% MSCI World", "60/40 (azioni/obbligazioni)"):
            _s, _ = cm.rendimenti_portafoglio_famoso(
                _bench, ss.period, ss.data_inizio, ss.data_fine, ss.valuta_base, ss.converti
            )
            if not _s.empty:
                dati_cum[_bench] = mtr.serie_cumulata(_s, base=100.0)
    _cum_r = pd.DataFrame(dati_cum).dropna()
    fig_r = px.line(_cum_r, labels={"value": "Indice (base 100)", "index": "Data", "variable": "Serie"})
    fig_r.update_traces(selector=dict(name="Il mio portafoglio"), line=dict(width=3.4, color="black"))
    fig_r.update_layout(hovermode="x unified", legend_title_text="Serie", margin=dict(t=20))
    st.plotly_chart(fig_r, width="stretch")
    st.caption(
        "Cosa significa per te: se la linea nera (il tuo portafoglio) sta sopra i benchmark, storicamente "
        "ha reso di più; se sta sotto, di meno. Conta l'andamento di lungo periodo, non i singoli mesi."
    )

    # Drawdown del portafoglio (quanto sei stato sotto il picco precedente).
    st.markdown("**Drawdown del portafoglio** (distanza dal massimo precedente)")
    dd_r = mtr.serie_drawdown(serie_pf_r)
    fig_ddr = px.area(dd_r, labels={"value": "Drawdown", "index": "Data"})
    fig_ddr.update_yaxes(tickformat=".0%")
    fig_ddr.update_layout(showlegend=False, margin=dict(t=20))
    st.plotly_chart(fig_ddr, width="stretch")
    st.caption(
        "Cosa significa per te: mostra quanto saresti stato 'sotto' rispetto al picco precedente. "
        "Le discese fanno parte del gioco: l'importante è l'orizzonte lungo."
    )
    # C3 — tempo di recupero / quanto a lungo sotto il picco.
    _sdd = mtr.statistiche_drawdown(serie_pf_r)
    if _sdd.get("valido"):
        _msg_dd = (
            f"⏳ Calo massimo **{_sdd['max_dd']:.1%}**; sei rimasto in perdita (sotto il picco) "
            f"al massimo per **~{_sdd['durata_max_mesi']:.0f} mesi** di fila."
        )
        if _sdd["in_perdita_ora"] and _sdd["mesi_perdita_ora"] >= 1:
            _msg_dd += f" In questo momento sei sotto il picco da ~{_sdd['mesi_perdita_ora']:.0f} mesi."
        st.caption(_msg_dd)

    # Verdetto diversificazione (geografica e settoriale) sintetico.
    _comp_r = cm.composizione_effettiva(tickers_ok)
    _dg = mtr.indice_diversificazione(mtr.aggrega_composizione(pesi, _comp_r, "paese")[0])
    _ds = mtr.indice_diversificazione(mtr.aggrega_composizione(pesi, _comp_r, "settore")[0])
    _parti = []
    if _dg.get("valido"):
        _parti.append(f"🌍 geografica **{_dg['livello']}** ({_dg['punteggio']}/100)")
    if _ds.get("valido"):
        _parti.append(f"🏭 settoriale **{_ds['livello']}** ({_ds['punteggio']}/100)")
    if _parti:
        st.markdown("**Diversificazione:** " + " · ".join(_parti)
                    + " — dettagli nella sezione 🌍 Allocazione.")

    # D5 — esporta / condividi.
    with st.expander("📤 Esporta / condividi"):
        _csv_pf = ss.selezionati[["Ticker", "Nome", "Peso %"]].to_csv(index=False).encode("utf-8")
        st.download_button("⬇️ Portafoglio (CSV)", _csv_pf, file_name="portafoglio_sharpe.csv",
                           mime="text/csv", key="dl_pf_csv")
        _df_met = pd.DataFrame({
            "Metrica": ["Rend. annuo (CAGR)", "Volatilità annua", "Sharpe", "Sortino",
                        "Max drawdown", "Rend. cumulato"],
            "Valore": [met_pf["Rend. annuo (CAGR)"], met_pf["Volatilità annua (covarianza)"],
                       met_pf["Sharpe"], met_pf["Sortino"], met_pf["Max drawdown"],
                       met_pf["Rend. cumulato"]],
        })
        st.download_button("⬇️ Metriche del Report (CSV)",
                           _df_met.to_csv(index=False).encode("utf-8"),
                           file_name="metriche_sharpe.csv", mime="text/csv", key="dl_met_csv")
        if st.button("🔗 Crea link condivisibile", key="btn_link_pf"):
            st.query_params["pf"] = cm.link_portafoglio(ss.selezionati)
        if "pf" in st.query_params:
            st.caption("✅ Link pronto: **copia l'indirizzo dalla barra del browser** (contiene `?pf=…`). "
                       "Chi lo apre ritrova questo stesso portafoglio.")
        st.caption("💡 Per un **PDF**: usa «Stampa → Salva come PDF» del browser.")

# === Singoli asset =========================================================
if sezione == "📈 Singoli asset":
    st.subheader("Metriche per singolo asset")
    met_asset = mtr.metriche_asset(rendimenti, risk_free).rename(index=nomi)
    st.dataframe(cm.formatta_metriche(met_asset), width="stretch")

    st.subheader("Andamento normalizzato (base 100)")
    cum = mtr.serie_cumulata(rendimenti, base=100.0).rename(columns=nomi_corti)
    fig = px.line(cum, labels={"value": "Indice (base 100)", "index": "Data", "variable": "Asset"})
    fig.update_layout(legend_title_text="Asset", hovermode="x unified")
    st.plotly_chart(fig, width="stretch")
    st.caption(
        "Cosa significa per te: tutte le linee partono da 100, così confronti la **crescita** dei vari "
        "asset a parità di partenza (il prezzo assoluto non conta)."
    )

    st.subheader("Drawdown")
    dd = pd.DataFrame({nomi_corti[t]: mtr.serie_drawdown(rendimenti[t]) for t in tickers_ok})
    fig_dd = px.area(dd, labels={"value": "Drawdown", "index": "Data", "variable": "Asset"})
    fig_dd.update_layout(legend_title_text="Asset", hovermode="x unified")
    fig_dd.update_yaxes(tickformat=".0%")
    st.plotly_chart(fig_dd, width="stretch")
    st.caption(
        "Cosa significa per te: quanto ogni asset è sceso rispetto al suo massimo precedente. Più la "
        "curva scende, più forti sono stati i cali da sopportare lungo il percorso."
    )

# === Portafoglio ===========================================================
if sezione == "💼 Portafoglio":
    st.subheader("Metriche del portafoglio")
    st.caption("Pesi normalizzati: " + ", ".join(f"{nomi[t]} {p:.1%}" for t, p in pesi.items()))

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Rend. annuo (CAGR)", f"{met_pf['Rend. annuo (CAGR)']:.2%}",
              help="Crescita media all'anno nel periodo. Più alto è meglio, ma guardalo col rischio.")
    c2.metric("Volatilità (covarianza)", f"{met_pf['Volatilità annua (covarianza)']:.2%}",
              help="Quanto oscilla il valore: <8% basso, 8–15% medio, >15% alto.")
    c3.metric("Sharpe", f"{met_pf['Sharpe']:.2f}",
              help="Rendimento per unità di rischio: >1 buono, >2 ottimo, <0 il rischio non ha pagato.")
    c4.metric("Sortino", f"{met_pf['Sortino']:.2f}",
              help="Come lo Sharpe ma conta solo le oscillazioni verso il basso (le perdite).")
    c5, c6, c7 = st.columns(3)
    c5.metric("Max drawdown", f"{met_pf['Max drawdown']:.2%}",
              help="Perdita massima dal picco al minimo successivo. Più vicino a 0 è meglio.")
    c6.metric("Rend. cumulato", f"{met_pf['Rend. cumulato']:.2%}",
              help="Guadagno totale nel periodo analizzato.")
    c7.metric("Volatilità (serie)", f"{met_pf['Volatilità annua (serie)']:.2%}",
              help="Volatilità calcolata sui rendimenti del portafoglio (di norma uguale a quella da covarianza).")
    _infl = ss.get("inflazione", 0.0)
    if _infl > 0 and not pd.isna(met_pf["Rend. annuo (CAGR)"]):
        cagr_reale = (1 + met_pf["Rend. annuo (CAGR)"]) / (1 + _infl) - 1
        st.caption(
            f"Rendimento **reale** (al netto di un'inflazione del {_infl:.1%}/anno): "
            f"**{cagr_reale:.2%}/anno** — la crescita effettiva del potere d'acquisto."
        )

    st.subheader("Portafoglio vs singoli asset (base 100)")
    serie_pf = mtr.serie_rendimenti_portafoglio(rendimenti, pesi)
    cum_all = mtr.serie_cumulata(rendimenti, base=100.0).rename(columns=nomi_corti)
    cum_all["PORTAFOGLIO"] = mtr.serie_cumulata(serie_pf, base=100.0)
    fig_cmp = px.line(cum_all, labels={"value": "Indice (base 100)", "index": "Data", "variable": "Serie"})
    fig_cmp.update_traces(line=dict(width=1.2))
    fig_cmp.update_traces(selector=dict(name="PORTAFOGLIO"), line=dict(width=3.5, color="black"))
    fig_cmp.update_layout(hovermode="x unified")
    st.plotly_chart(fig_cmp, width="stretch")
    st.caption(
        "Cosa significa per te: la linea nera è il **tuo portafoglio**; le altre sono i singoli asset. "
        "Se la nera è più «liscia» dei singoli, la diversificazione sta smorzando le oscillazioni."
    )

    # Confronto sempre disponibile con benchmark di riferimento.
    st.subheader("Portafoglio vs benchmark di riferimento (base 100)")
    serie_bench = {"Il mio portafoglio": serie_pf}
    with st.spinner("Carico i benchmark..."):
        for nome_b in ["100% MSCI World", "60/40 (azioni/obbligazioni)"]:
            sb, _ = cm.rendimenti_portafoglio_famoso(
                nome_b, ss.period, ss.data_inizio, ss.data_fine, ss.valuta_base, ss.converti)
            if not sb.empty:
                serie_bench[nome_b] = sb
    df_bench = pd.DataFrame(serie_bench).dropna()
    if df_bench.shape[1] >= 2:
        cum_b = mtr.serie_cumulata(df_bench, base=100.0)
        fig_b = px.line(cum_b, labels={"value": "Indice (base 100)", "index": "Data", "variable": "Serie"})
        fig_b.update_traces(line=dict(width=1.4))
        fig_b.update_traces(selector=dict(name="Il mio portafoglio"), line=dict(width=3.2, color="black"))
        fig_b.update_layout(hovermode="x unified")
        st.plotly_chart(fig_b, width="stretch")
        st.dataframe(cm.formatta_metriche(mtr.metriche_asset(df_bench, risk_free)), width="stretch")
        st.caption(
            "Riferimenti: **100% MSCI World** (tutte le azioni mondiali) e **60/40** "
            "(60% azioni, 40% obbligazioni). Allineati sul periodo comune."
        )
    else:
        st.caption("Benchmark non disponibili per questo periodo.")

    col_a, col_b = st.columns(2)
    with col_a:
        st.subheader("Matrice di correlazione")
        corr_grezza = mtr.matrice_correlazione(rendimenti)
        corr = corr_grezza.rename(index=nomi_corti, columns=nomi_corti)
        fig_corr = px.imshow(corr, text_auto=".2f", color_continuous_scale="RdBu_r", zmin=-1, zmax=1, aspect="auto")
        fig_corr.update_layout(height=max(360, 70 * len(corr) + 140), margin=dict(t=20, l=10, r=10),
                               coloraxis_colorbar=dict(title="corr"))
        fig_corr.update_xaxes(tickangle=-30)
        st.plotly_chart(fig_corr, width="stretch")
        st.caption(
            "Cosa significa per te: valori vicini a 1 = asset che si muovono insieme (poca "
            "diversificazione); vicini a 0 o negativi = si muovono in modo diverso (più diversificazione)."
        )
        # Alert su asset molto sovrapposti.
        cols_c = list(corr_grezza.columns)
        coppie = [(cols_c[ii], cols_c[jj], corr_grezza.iloc[ii, jj])
                  for ii in range(len(cols_c)) for jj in range(ii + 1, len(cols_c))
                  if corr_grezza.iloc[ii, jj] > 0.9]
        if coppie:
            righe = "; ".join(f"**{nomi.get(a, a)}** ↔ **{nomi.get(b, b)}** ({c:.0%})" for a, b, c in coppie)
            st.warning(
                f"⚠️ Asset molto sovrapposti (correlazione > 90%): {righe}. "
                "Si muovono quasi insieme: tenerli entrambi aggiunge poca diversificazione."
            )
    with col_b:
        st.subheader("Contributo al rischio")
        rc = mtr.contributo_rischio(rendimenti, pesi).rename(index=nomi)
        rc_plot = rc.reset_index().rename(columns={"index": "Asset"})
        rc_plot["Asset"] = rc_plot["Asset"].map(cm.etichetta_corta)
        fig_rc = px.bar(rc_plot, x="Asset", y="Contributo %", text=rc_plot["Contributo %"].map(lambda v: f"{v:.1%}"))
        fig_rc.update_yaxes(tickformat=".0%")
        fig_rc.update_layout(showlegend=False)
        st.plotly_chart(fig_rc, width="stretch")
        st.caption(
            "Cosa significa per te: quanto ciascun asset contribuisce al rischio (volatilità) totale. "
            "Se un asset contribuisce **meno** del suo peso, sta diversificando bene."
        )
        st.dataframe(
            rc.style.format(
                {"Peso": "{:.2%}", "Contributo marginale": "{:.4f}",
                 "Contributo assoluto": "{:.4f}", "Contributo %": "{:.2%}"}
            ),
            width="stretch",
        )

# === Allocazione ===========================================================
if sezione == "🌍 Allocazione":
    st.subheader("Composizione per classe di attività (asset class)")
    st.caption(
        "Recuperata **automaticamente** da Yahoo (azioni / obbligazioni / liquidità). "
        "Oro e materie prime spesso finiscono in «Altro»."
    )
    ac_map = cm.carica_asset_classes(tuple(tickers_ok))
    if not ac_map:
        st.caption("Dati di asset class non disponibili per questi asset.")
    else:
        comp_ac = {t: {"asset_class": classi} for t, classi in ac_map.items()}
        serie_ac, mancanti_ac = mtr.aggrega_composizione(pesi, comp_ac, "asset_class")
        if mancanti_ac:
            st.caption("Asset class non disponibile per: " + ", ".join(nomi.get(t, t) for t in mancanti_ac))
        if not serie_ac.empty:
            ca1, ca2 = st.columns(2)
            with ca1:
                fig_ac = px.pie(values=serie_ac.values, names=serie_ac.index, hole=0.35)
                fig_ac.update_traces(textposition="inside", textinfo="percent+label")
                st.plotly_chart(fig_ac, width="stretch")
            with ca2:
                df_ac = serie_ac.reset_index()
                df_ac.columns = ["Classe", "Peso"]
                fig_acb = px.bar(df_ac, x="Peso", y="Classe", orientation="h")
                fig_acb.update_xaxes(tickformat=".0%")
                fig_acb.update_layout(yaxis={"categoryorder": "total ascending"})
                st.plotly_chart(fig_acb, width="stretch")
            st.caption(
                "Cosa significa per te: la divisione tra **azioni, obbligazioni e liquidità**. Più azioni "
                "= più potenziale di crescita ma più oscillazioni; più obbligazioni = più stabilità."
            )

    st.divider()
    st.subheader("Composizione per paese e settore")
    st.info(
        "Per i principali ETF/indici la ripartizione **geografica e settoriale** è già inclusa in un "
        "**dataset interno** (stime indicative dai factsheet) e viene usata **in automatico**. Puoi "
        "comunque correggerla o aggiungerla a mano (o da CSV) qui sotto: la tua versione ha la precedenza."
    )

    cbtn1, cbtn2 = st.columns(2)
    with cbtn1:
        if st.button("🔄 Recupera settori da yfinance", width="stretch"):
            settori = cm.carica_settori(tuple(tickers_ok))
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
    comp_edit = st.data_editor(
        cm.comp_to_dataframe(ss.composizione),
        num_rows="dynamic",
        width="stretch",
        key="editor_comp",
        column_config={
            "Tipo": st.column_config.SelectboxColumn("Tipo", options=["paese", "settore"]),
            "Peso": st.column_config.NumberColumn("Peso", min_value=0.0, max_value=1.0, step=0.01),
        },
    )
    ss.composizione = cm.dataframe_to_comp(comp_edit)
    st.download_button(
        "⬇️ Scarica composizione (CSV)",
        data=dati.composizione_in_csv(ss.composizione),
        file_name="composizione.csv",
        mime="text/csv",
    )

    st.divider()

    # Composizione effettiva: manuale (override) oppure dataset interno.
    comp_eff = cm.composizione_effettiva(tickers_ok)

    # Alert di sovrapposizione: asset azionari che espongono agli stessi mercati.
    equity = {t for t in tickers_ok if ac_map.get(t, {}).get("Azioni", 0.0) >= 0.5}
    distrib_paese = {t: comp_eff[t]["paese"] for t in equity
                     if comp_eff.get(t, {}).get("paese")}
    coppie_ov = mtr.coppie_sovrapposte(distrib_paese, soglia=0.9)
    if coppie_ov:
        righe = "; ".join(f"**{nomi.get(a, a)}** ↔ **{nomi.get(b, b)}** ({s:.0%} simili)"
                          for a, b, s in coppie_ov)
        st.warning(
            f"⚠️ **Sovrapposizione**: {righe}. Questi asset azionari espongono in gran parte "
            "agli **stessi mercati/aziende** (es. un indice mondiale contiene già gran parte dell'S&P 500): "
            "tenerli entrambi aggiunge poca diversificazione."
        )

    # Aggregazione unica per paese e settore (riusata per verdetto e grafici).
    agg = {t: mtr.aggrega_composizione(pesi, comp_eff, t) for t in ("paese", "settore")}

    # --- Verdetto di diversificazione (geografica e settoriale) ---
    st.subheader("🧭 Quanto sei diversificato?")
    st.caption(
        "Sintesi di quanto il portafoglio è distribuito tra **aree geografiche** e **settori**. "
        "Più alto il punteggio, **meno dipendi** da un singolo paese o settore."
    )
    cdiv = st.columns(2)
    for col, t, etichetta, parola in (
        (cdiv[0], "paese", "🌍 Geografica", "aree"),
        (cdiv[1], "settore", "🏭 Settoriale", "settori"),
    ):
        info = mtr.indice_diversificazione(agg[t][0])
        with col:
            if not info["valido"]:
                st.markdown(f"**{etichetta}**")
                st.caption("Composizione non disponibile per questi asset.")
                continue
            _emoji = {"buona": "🟢", "media": "🟡", "bassa": "🔴"}[info["livello"]]
            st.markdown(
                f"**{etichetta}** — {_emoji} diversificazione **{info['livello']}** "
                f"(**{info['punteggio']}/100**)"
            )
            st.markdown(
                f"Quota principale: **{info['top_categoria']} {info['top_peso']:.0%}**.  \n"
                f"≈ **{info['numero_effettivo']:.1f} {parola}** ben distribuiti "
                f"(su {info['n_categorie']} presenti)."
            )
    st.divider()

    for tipo, titolo in (("paese", "Distribuzione per paese"), ("settore", "Distribuzione per settore")):
        st.subheader(titolo)
        serie, mancanti = agg[tipo]
        if mancanti:
            st.caption(
                f"Composizione **{tipo}** non disponibile per: "
                f"{', '.join(nomi.get(t, t) for t in mancanti)} (esclusi dall'aggregazione; "
                "aggiungila a mano qui sopra per includerli)."
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
        st.caption(
            f"Cosa significa per te: è la tua esposizione reale per **{tipo}**. Se una sola voce pesa "
            "molto (es. oltre il 60%), dipendi parecchio da quel singolo mercato."
        )

# === Timing (rolling returns) =============================================
if sezione == "⏱️ Timing":
    st.subheader("Quanto avrebbe reso, a seconda di quando avresti investito")
    st.caption(
        "Ogni punto risponde a: «se avessi investito in **questo** giorno e tenuto il "
        "portafoglio per la finestra scelta, quanto avrei guadagnato **in media all'anno**?». "
        "Serve a capire quanto conta il *momento* in cui si entra. Usa **tutto** lo storico "
        "disponibile (non l'intervallo nella barra laterale)."
    )

    # Scarica tutto lo storico comune disponibile per il portafoglio (cache).
    with st.spinner("Calcolo i rendimenti su tutto lo storico..."):
        ris_max = cm.carica_dati(tuple(tickers_ok), "max", None, None, ss.valuta_base, ss.converti)

    if ris_max.prezzi.empty:
        st.warning("Storico non disponibile per il calcolo.")
    else:
        rend_max = mtr.rendimenti_giornalieri(ris_max.prezzi)
        serie_pf_max = mtr.serie_rendimenti_portafoglio(rend_max, pesi)
        anni_storico = (ris_max.prezzi.index.max() - ris_max.prezzi.index.min()).days / 365.25

        FINESTRE = {"1 anno": 1, "3 anni": 3, "5 anni": 5, "10 anni": 10,
                    "15 anni": 15, "20 anni": 20, "Massima": None}
        scelta_fin = st.radio(
            "Finestra di investimento", list(FINESTRE.keys()), index=2, horizontal=True,
            help="Per quanti anni tieni l'investimento dopo averlo iniziato. «Massima» = la "
                 "finestra più lunga possibile con lo storico disponibile.",
        )
        anni_fin = FINESTRE[scelta_fin]
        if anni_fin is None:  # "Massima"
            anni_fin = max(1, int(anni_storico) - 1)

        roll = mtr.rolling_rendimenti_annualizzati(serie_pf_max, anni_fin)
        if roll.empty:
            st.warning(
                f"Storico insufficiente: servono più di **{anni_fin} anni** di dati comuni a tutti "
                f"gli asset, ma ne risultano circa **{anni_storico:.1f}**. Prova una finestra più corta."
            )
        else:
            # Statistiche di sintesi.
            peggiore, mediana, migliore = roll.min(), roll.median(), roll.max()
            quota_pos = float((roll > 0).mean())
            s1, s2, s3, s4, s5 = st.columns(5)
            s1.metric("Peggiore", f"{peggiore:.2%}/anno", help="Il risultato peggiore tra tutti i giorni di partenza possibili.")
            s2.metric("Mediana", f"{mediana:.2%}/anno", help="Il valore centrale: metà dei casi è sopra, metà sotto.")
            s3.metric("Migliore", f"{migliore:.2%}/anno", help="Il risultato migliore tra tutti i giorni di partenza possibili.")
            s4.metric("Finestre positive", f"{quota_pos:.0%}", help="Quota di giorni di partenza che hanno chiuso in guadagno.")
            s5.metric("Finestre in perdita", f"{1 - quota_pos:.0%}", help="Quota di giorni di partenza che hanno chiuso in perdita.")

            fig_roll = go.Figure()
            fig_roll.add_trace(go.Scatter(
                x=roll.index, y=roll.values, mode="lines",
                name=f"Rend. annuo su {anni_fin} anni", line=dict(color="#1f77b4", width=1.6),
                fill="tozeroy", fillcolor="rgba(31,119,180,0.12)",
            ))
            fig_roll.add_hline(y=float(mediana), line_dash="dash", line_color="orange",
                               annotation_text=f"mediana {mediana:.1%}", annotation_position="top left")
            fig_roll.add_hline(y=0, line_color="gray", opacity=0.5)
            fig_roll.update_yaxes(tickformat=".0%", title_text=f"Rendimento medio annuo (finestra {anni_fin} anni)")
            fig_roll.update_xaxes(title_text="Giorno in cui avresti investito")
            fig_roll.update_layout(hovermode="x unified", margin=dict(t=20))
            st.plotly_chart(fig_roll, width="stretch")
            st.caption(
                "Cosa significa per te: ogni punto è un possibile giorno d'ingresso; la nuvola mostra che "
                "il **momento** in cui entri pesa sempre meno man mano che l'orizzonte si allunga."
            )
            st.caption(
                f"{len(roll)} possibili giorni di partenza analizzati su ~{anni_storico:.1f} anni di storico. "
                "⚠️ I rendimenti passati non garantiscono quelli futuri."
            )

            # C2 — distribuzione dei risultati + messaggio "time in market".
            st.markdown("**Distribuzione dei risultati** (tutte le finestre possibili)")
            fig_dist = px.histogram(roll, nbins=30, labels={"value": "Rendimento medio annuo"})
            fig_dist.add_vline(x=float(mediana), line_dash="dash", line_color="orange",
                               annotation_text=f"mediana {mediana:.1%}")
            fig_dist.add_vline(x=0, line_color="gray", opacity=0.6)
            fig_dist.update_xaxes(tickformat=".0%")
            fig_dist.update_layout(showlegend=False, bargap=0.05, margin=dict(t=20))
            st.plotly_chart(fig_dist, width="stretch")
            st.caption(
                "Cosa significa per te: più le barre stanno a **destra dello zero**, più spesso questa "
                f"finestra di {anni_fin} anni ha chiuso in guadagno. È l'idea di **«time in market» batte "
                "«timing the market»**: contare sul tempo, non sull'azzeccare il momento."
            )

            # C4 — costo di restare fuori nei giorni migliori (anti-timing).
            _cmg = mtr.costo_perdere_migliori_giorni(serie_pf_max, 10)
            if _cmg.get("valido"):
                st.markdown("**E se provi a fare «timing» e perdi i 10 giorni migliori?**")
                _cc1, _cc2 = st.columns(2)
                _cc1.metric("Sempre investito", f"{_cmg['tot']:.0%}",
                            help="Rendimento totale dell'intero storico, restando sempre investito.")
                _cc2.metric("Senza i 10 giorni migliori", f"{_cmg['tot_senza']:.0%}",
                            f"{_cmg['tot_senza'] - _cmg['tot']:+.0%}",
                            help="Stesso periodo, ma saltando i 10 giorni di rialzo più forti.")
                st.caption(
                    "Cosa significa per te: gran parte del guadagno arriva in **pochissimi giorni**, "
                    "spesso a sorpresa subito dopo i cali. Uscire e rientrare rischia di **farteli "
                    "perdere**: per questo, da passivo, conviene restare investiti."
                )

# === PAC / DCA (backtest storico) =========================================
if sezione == "💶 PAC":
    st.subheader("Simulatore PAC (versamenti periodici) — backtest storico")
    st.caption(
        "Simula di aver investito una cifra fissa a intervalli regolari **nel passato**, sui dati "
        "reali del tuo portafoglio, e la confronta con un investimento unico iniziale dello stesso "
        "totale. Usa tutto lo storico disponibile."
    )
    cpac1, cpac2 = st.columns(2)
    importo_pac = cpac1.number_input(
        "Importo per versamento (€)", min_value=10.0, value=100.0, step=10.0,
        help="Quanto versi ogni volta (es. ogni mese).",
    )
    freq_label = cpac2.selectbox(
        "Frequenza versamenti", ["Mensile", "Bimestrale", "Trimestrale", "Semestrale", "Annuale"],
        help="Ogni quanto tempo versi l'importo indicato.",
    )
    freq_map = {"Mensile": 1, "Bimestrale": 2, "Trimestrale": 3, "Semestrale": 6, "Annuale": 12}

    with st.spinner("Calcolo il PAC su tutto lo storico..."):
        ris_pac = cm.carica_dati(tuple(tickers_ok), "max", None, None, ss.valuta_base, ss.converti)
    if ris_pac.prezzi.empty:
        st.warning("Storico non disponibile per il calcolo.")
    else:
        serie_pf_pac = mtr.serie_rendimenti_portafoglio(mtr.rendimenti_giornalieri(ris_pac.prezzi), pesi)
        res_pac = mtr.simula_pac(serie_pf_pac, importo_pac, freq_map[freq_label])
        if res_pac is None:
            st.warning("Dati insufficienti per la simulazione.")
        else:
            val = ss.valuta_base if ss.converti else ""
            m1, m2, m3, m4 = st.columns(4)
            m1.metric("Capitale versato", f"{res_pac['versato']:,.0f} {val}",
                      help="La somma di tutti i tuoi versamenti.")
            m2.metric("Valore finale (PAC)", f"{res_pac['valore_finale']:,.0f} {val}",
                      f"{res_pac['guadagno_pct']:+.1%}", help="Quanto varrebbe oggi il PAC, e il guadagno %.")
            m3.metric("Investimento unico", f"{res_pac['lump_finale']:,.0f} {val}",
                      f"{res_pac['lump_guadagno_pct']:+.1%}",
                      help="Se avessi investito tutto il capitale finale all'inizio, in un colpo solo.")
            m4.metric("N. versamenti", f"{res_pac['n_versamenti']}", help="Quante volte avresti versato.")
            fig_pac = px.line(res_pac["serie"], labels={"value": f"Valore ({val})", "index": "Data", "variable": ""})
            fig_pac.update_layout(hovermode="x unified", legend_title_text="")
            st.plotly_chart(fig_pac, width="stretch")
            st.caption(
                "Il PAC riduce il rischio di «entrare nel momento sbagliato»; l'investimento unico, però, "
                "storicamente rende spesso di più perché i soldi restano investiti più a lungo. "
                "⚠️ Backtest storico, non una previsione."
            )

# === Proiezione a obiettivo ================================================
if sezione == "🎯 Obiettivo":
    st.subheader("Proiezione a obiettivo")
    st.caption(
        "Quanto dovresti versare ogni mese per raggiungere una certa cifra, usando rendimento e "
        "volatilità **storici** del tuo portafoglio. Stima statistica con scenari, non una garanzia."
    )
    co1, co2, co3 = st.columns(3)
    obiettivo_eur = co1.number_input(
        "Obiettivo (€)", min_value=1000.0, value=100000.0, step=1000.0,
        help="La cifra che vorresti raggiungere.",
    )
    prob_perc = co2.slider(
        "Probabilità di riuscita", min_value=50, max_value=95, value=75, step=5, format="%d%%",
        help="Quanto vuoi andare «sul sicuro». Più alta = versamento mensile più alto, ma più "
             "probabilità di centrare l'obiettivo anche se i mercati vanno male.",
    )
    co3.metric("Orizzonte", f"{orizzonte} anni", help="Si imposta nella barra laterale.")

    with st.spinner("Simulo gli scenari..."):
        ris_obj = cm.carica_dati(tuple(tickers_ok), "max", None, None, ss.valuta_base, ss.converti)
    if ris_obj.prezzi.empty:
        st.warning("Storico non disponibile per il calcolo.")
    else:
        serie_pf_obj = mtr.serie_rendimenti_portafoglio(mtr.rendimenti_giornalieri(ris_obj.prezzi), pesi)
        mu = mtr.cagr(serie_pf_obj)
        sigma = mtr.volatilita_annua(serie_pf_obj)
        reali = bool(ss.get("reali"))
        mu_use = ((1 + mu) / (1 + ss.get("inflazione", 0.0)) - 1) if reali else mu
        nota_infl = (f" → **reale {mu_use:.1%}/anno** (tolta inflazione {ss.get('inflazione', 0.0):.1%})") if reali else ""
        st.caption(f"Ipotesi dal tuo portafoglio: rendimento storico **{mu:.1%}/anno**, volatilità **{sigma:.1%}**{nota_infl}.")
        if reali:
            st.info("📉 Importi mostrati in **€ di oggi** (al netto dell'inflazione): è il potere d'acquisto reale.")
        proj = mtr.proiezione_obiettivo(mu_use, sigma, obiettivo_eur, orizzonte, prob_perc / 100.0)
        if proj is None:
            st.warning("Parametri non validi.")
        else:
            val = ss.valuta_base if ss.converti else ""
            mc1, mc2 = st.columns(2)
            mc1.metric(
                f"Versamento mensile (per riuscire ~{proj['prob_target']:.0%})",
                f"{proj['pmt_mensile']:,.0f} {val}",
                help="Quanto versare ogni mese per raggiungere l'obiettivo con la probabilità scelta.",
            )
            mc2.metric("Probabilità stimata di riuscita", f"{proj['prob_effettiva']:.0%}",
                       help="Quota di scenari simulati in cui l'obiettivo viene raggiunto con quel versamento.")
            sc1, sc2, sc3 = st.columns(3)
            sc1.metric("Scenario pessimista", f"{proj['pessimista']:,.0f} {val}",
                       help="Tra i casi peggiori (10° percentile delle simulazioni).")
            sc2.metric("Scenario medio", f"{proj['medio']:,.0f} {val}", help="Il caso centrale (50%).")
            sc3.metric("Scenario ottimista", f"{proj['ottimista']:,.0f} {val}",
                       help="Tra i casi migliori (90° percentile delle simulazioni).")
            bande = proj["bande"].copy()
            bande.index = bande.index / 12.0
            fig_obj = px.line(bande, labels={"value": f"Valore ({val})", "index": "Anni", "variable": ""})
            fig_obj.add_hline(y=obiettivo_eur, line_dash="dot", line_color="green", annotation_text="obiettivo")
            fig_obj.update_layout(hovermode="x unified", legend_title_text="")
            st.plotly_chart(fig_obj, width="stretch")
            st.caption(
                "Cosa significa per te: la banda mostra dove potrebbe arrivare il capitale nei vari scenari "
                "(da pessimista a ottimista); la linea verde è l'obiettivo. Conta la **tendenza**, non il "
                "singolo numero."
            )
            st.caption("⚠️ Simulazione statistica (Monte Carlo) su ipotesi storiche: il futuro può essere diverso.")

# === Costi (TER) e fiscalità ==============================================
if sezione == "💰 Costi e tasse":
    st.subheader("Costi (TER) e fiscalità — stime didattiche")
    st.caption(
        "TER (costo annuo) e **aliquota** fiscale **per singolo asset**. L'aliquota è impostata in "
        "**automatico** (12,5% per gli ETF di **titoli di Stato** riconosciuti, 26% per il resto) e "
        "puoi modificarla. In Italia c'è anche il **bollo 0,2%/anno**."
    )
    righe_costi = []
    for t in tickers_ok:
        c = ss.costi.get(t, {})
        aliq_default = 12.5 if dsc.is_titolo_stato(t) else 26.0
        righe_costi.append({"Ticker": t, "Asset": nomi.get(t, t),
                            "TER %": float(c.get("ter", 0.20)),
                            "Aliquota %": float(c.get("aliquota", aliq_default))})
    df_costi = st.data_editor(
        pd.DataFrame(righe_costi), width="stretch", key="editor_costi", hide_index=True,
        column_config={
            "Ticker": st.column_config.TextColumn("Ticker", disabled=True),
            "Asset": st.column_config.TextColumn("Asset", disabled=True),
            "TER %": st.column_config.NumberColumn(
                "TER %", min_value=0.0, max_value=5.0, step=0.01,
                help="Costo annuo dell'ETF, lo trovi nel KID (es. 0,20%)."),
            "Aliquota %": st.column_config.NumberColumn(
                "Aliquota %", min_value=0.0, max_value=43.0, step=0.5,
                help="26% azioni e obbligazioni societarie; 12,5% titoli di Stato/white-list."),
        },
    )
    ter_pesato, aliq_pesata = 0.0, 0.0
    for _, rr in df_costi.iterrows():
        t = rr["Ticker"]
        ss.costi[t] = {"ter": float(rr["TER %"]), "aliquota": float(rr["Aliquota %"])}
        w = float(pesi.get(t, 0.0))
        ter_pesato += w * float(rr["TER %"]) / 100.0
        aliq_pesata += w * float(rr["Aliquota %"]) / 100.0
    st.caption(f"TER medio del portafoglio: **{ter_pesato:.2%}/anno** · aliquota media: **{aliq_pesata:.1%}**.")

    importo_c = st.number_input(
        "Capitale di esempio (€)", min_value=100.0, value=10000.0, step=100.0,
        help="Su quale capitale calcolare l'impatto di costi e tasse nel tempo.")
    serie_pf_c = mtr.serie_rendimenti_portafoglio(rendimenti, pesi)
    rendimento_lordo = mtr.cagr(serie_pf_c)
    if pd.isna(rendimento_lordo):
        rendimento_lordo = 0.05
    st.caption(f"Ipotesi di rendimento lordo: **{rendimento_lordo:.1%}/anno** (storico del portafoglio).")

    orizzonti = sorted({10, 20, int(orizzonte)})
    cols_anni = st.columns(len(orizzonti))
    for col, anni_c in zip(cols_anni, orizzonti):
        res_c = mtr.proiezione_costi(importo_c, rendimento_lordo, ter_pesato, aliq_pesata, anni_c)
        with col:
            st.markdown(f"**A {anni_c} anni**")
            st.metric("Valore lordo", f"{res_c['val_lordo']:,.0f} €", help="Senza costi né tasse.")
            st.metric("Costo del TER", f"−{res_c['costo_ter']:,.0f} €", help="Quanto ti sarebbe costato il TER.")
            st.metric("Tasse stimate", f"−{res_c['tasse']:,.0f} €", help="Tasse sul guadagno, alla vendita.")
            st.metric("Valore netto", f"{res_c['val_netto']:,.0f} €", help="Dopo TER, bollo e tasse.")
    # C5 — impatto CUMULATO del TER nel tempo (effetto composto), in €.
    st.markdown("**Quanto ti «mangia» il TER nel tempo** (costo cumulato, €)")
    anni_max_c = max(orizzonti)
    righe_ter = []
    for a in range(1, anni_max_c + 1):
        rc = mtr.proiezione_costi(importo_c, rendimento_lordo, ter_pesato, aliq_pesata, a)
        righe_ter.append({"Anni": a, "Costo cumulato del TER (€)": rc["costo_ter"]})
    df_ter = pd.DataFrame(righe_ter).set_index("Anni")
    fig_ter = px.area(df_ter, labels={"value": "Costo del TER (€)", "Anni": "Anni"})
    fig_ter.update_layout(showlegend=False, margin=dict(t=20))
    st.plotly_chart(fig_ter, width="stretch")
    st.caption(
        f"Cosa significa per te: con un TER medio dello **{ter_pesato:.2%}/anno**, in {anni_max_c} anni "
        "il costo non è una sommetta fissa: cresce in modo **composto**, perché ogni anno rinunci anche "
        "al rendimento che quei soldi avrebbero prodotto."
    )

    # C6 — fiscalità italiana (didattica), con la specificità degli ETF armonizzati.
    with st.expander("🇮🇹 Fiscalità ETF in Italia — in breve (didattico)"):
        st.markdown(
            "- **Aliquota**: **26%** sui guadagni; **12,5%** sulla quota in **titoli di Stato** italiani "
            "e *white list* (e relativi ETF).\n"
            "- **Imposta di bollo**: **0,2%/anno** sul controvalore (con intermediario italiano; con "
            "intermediario estero si applica l'**IVAFE**, equivalente).\n"
            "- **ETF armonizzati (UCITS) — quirk importante**: i **guadagni** sono «**redditi di "
            "capitale**», le **perdite** (minusvalenze) sono «**redditi diversi**». I due «cassetti» "
            "**non si compensano** tra loro: **non** puoi usare minusvalenze pregresse per abbattere il "
            "guadagno di un ETF, né compensare la perdita di un ETF col guadagno di un altro ETF. Le "
            "minusvalenze restano però utilizzabili (entro **4 anni**) contro altri *redditi diversi* "
            "(es. plusvalenze su azioni singole o certificati).\n"
            "- **Regime amministrato**: con la maggior parte dei broker italiani le tasse sono trattenute "
            "**in automatico** (sostituto d'imposta).\n\n"
            "_Questa app usa una stima semplice (aliquota × guadagno) e **non** modella la compensazione "
            "minus/plus._"
        )
    st.caption(
        "⚠️ Stima **didattica**, non consulenza fiscale: le regole possono cambiare e i casi personali "
        "variano. Verifica sempre con fonti ufficiali o un professionista."
    )

# === Dividendi / rendita ===================================================
if sezione == "💸 Dividendi":
    st.subheader("Dividendi / rendita stimata")
    st.caption(
        "Stima della **rendita annua da dividendi/cedole** del portafoglio (dati Yahoo). "
        "Gli ETF ad **accumulazione** risultano ~0 perché **reinvestono** i dividendi invece di "
        "pagarli in contanti: il rendimento c'è, ma resta dentro l'ETF."
    )
    capitale_div = st.number_input(
        "Capitale investito (€)", min_value=100.0, value=10000.0, step=100.0,
        help="Su quale capitale stimare la rendita annua da dividendi.")

    righe_div, yield_pesato, lordo_tot, netto_tot = [], 0.0, 0.0, 0.0
    with st.spinner("Stimo i dividendi..."):
        for t in tickers_ok:
            y = cm.rendimento_dividendo(t)
            w = float(pesi.get(t, 0.0))
            aliq = float(ss.costi.get(t, {}).get(
                "aliquota", 12.5 if dsc.is_titolo_stato(t) else 26.0)) / 100.0
            lordo = capitale_div * w * y
            netto = lordo * (1.0 - aliq)
            yield_pesato += w * y
            lordo_tot += lordo
            netto_tot += netto
            righe_div.append({"Asset": nomi.get(t, t), "Yield": y,
                              "Rendita lorda (€)": lordo, "Rendita netta (€)": netto})

    md1, md2, md3 = st.columns(3)
    md1.metric("Yield medio portafoglio", f"{yield_pesato:.2%}",
               help="Rendita annua da dividendi in percentuale del capitale.")
    md2.metric("Rendita annua lorda", f"{lordo_tot:,.0f} €",
               help="Dividendi/cedole stimati in un anno, al lordo delle tasse.")
    md3.metric("Rendita annua netta", f"{netto_tot:,.0f} €",
               help="Al netto dell'imposta italiana (26%, oppure 12,5% sui titoli di Stato).")
    st.dataframe(
        pd.DataFrame(righe_div).style.format(
            {"Yield": "{:.2%}", "Rendita lorda (€)": "{:,.0f}", "Rendita netta (€)": "{:,.0f}"}),
        width="stretch",
    )
    st.caption(
        "⚠️ Stima dai dati Yahoo (dividendi degli ultimi 12 mesi ÷ prezzo): può mancare o variare nel "
        "tempo, e non considera l'eventuale ritenuta estera alla fonte. A scopo didattico."
    )

# === Ribilanciamento vs buy & hold ========================================
if sezione == "♻️ Ribilanciamento":
    st.subheader("Ribilanciamento vs «compra e tieni»")
    st.caption(
        "Confronta il lasciare il portafoglio com'è (**buy & hold**: i pesi cambiano da soli) "
        "col **ribilanciarlo** periodicamente per riportarlo ai pesi scelti. Usa tutto lo storico."
    )
    modo_label = st.radio(
        "Strategia di ribilanciamento", ["Annuale", "A soglia"], horizontal=True,
        help="Annuale: ogni 12 mesi. A soglia: quando un peso si scosta troppo dal target.")
    soglia = 0.05
    if modo_label == "A soglia":
        soglia = st.slider(
            "Soglia di scostamento (%)", 2, 20, 5, 1,
            help="Ribilancia quando un peso supera questo scostamento dai pesi target.") / 100.0

    with st.spinner("Simulo le due strategie..."):
        ris_rib = cm.carica_dati(tuple(tickers_ok), "max", None, None, ss.valuta_base, ss.converti)
    if ris_rib.prezzi.empty:
        st.warning("Storico non disponibile per il calcolo.")
    else:
        modo = "annuale" if modo_label == "Annuale" else "soglia"
        res_rib = mtr.simula_ribilanciamento(ris_rib.prezzi, pesi, modo, soglia)
        serie_rib = res_rib["serie"]
        if serie_rib.empty:
            st.warning("Dati insufficienti per la simulazione.")
        else:
            fig_rib = px.line(serie_rib, labels={"value": "Indice (base 100)", "index": "Data", "variable": "Strategia"})
            fig_rib.update_layout(hovermode="x unified")
            st.plotly_chart(fig_rib, width="stretch")
            st.caption(
                "Cosa significa per te: se le due linee sono vicine, ribilanciare cambia poco; il "
                "ribilanciamento serve soprattutto a **tenere il rischio sotto controllo**, non per forza "
                "a guadagnare di più."
            )
            met_rib = mtr.metriche_asset(mtr.rendimenti_giornalieri(serie_rib), risk_free)
            st.dataframe(cm.formatta_metriche(met_rib), width="stretch")
            st.caption(
                f"Numero di ribilanci: **{res_rib['n_ribilanci']}**. "
                "⚠️ Non sono inclusi costi di transazione o tasse sui ribilanci (analisi didattica)."
            )

# === Lettura statistica del portafoglio ===================================
if sezione == "📊 Statistica":
    st.subheader("Lettura statistica del portafoglio")
    st.caption(
        "Indicatori calcolati **sul portafoglio nel suo insieme**, usando tutto lo storico comune "
        "disponibile. (Il semaforo risk-on/off generale di mercato è in cima all'app.)"
    )
    with st.spinner("Calcolo gli indicatori sul portafoglio..."):
        ris_stat = cm.carica_dati(tuple(tickers_ok), "max", None, None, ss.valuta_base, ss.converti)
    if ris_stat.prezzi.empty:
        st.warning("Storico non disponibile per il calcolo.")
    else:
        rend_stat = mtr.rendimenti_giornalieri(ris_stat.prezzi)
        serie_pf_stat = mtr.serie_rendimenti_portafoglio(rend_stat, pesi)
        ricchezza_pf = mtr.serie_cumulata(serie_pf_stat, base=100.0)
        cm.mostra_lettura_statistica(ricchezza_pf, serie_pf_stat, risk_free, chiave="portafoglio")

# === Ottimizzazione ========================================================
if sezione == "🧮 Ottimizzazione":
    st.subheader("Ottimizzazione del portafoglio")
    if len(tickers_ok) < 2:
        st.info("Servono almeno 2 asset per l'ottimizzazione.")
    else:
        OBIETTIVI = {
            "Minima varianza (minimo rischio)": "min_var",
            "Risk parity (parità di rischio)": "risk_parity",
            "Massima diversificazione (decorrelazione)": "max_decorr",
            "Massimo indice di Sharpe (tangenza)": "max_sharpe",
            "Massimo rendimento annuo": "max_ret",
        }
        col_ob, col_lo = st.columns([2, 1])
        scelta = col_ob.selectbox(
            "Obiettivo", list(OBIETTIVI.keys()), index=0,
            help="Minima varianza = minor rischio. Risk parity = ogni asset contribuisce ugualmente "
                 "al rischio. Massima diversificazione = sfrutta al meglio gli asset poco correlati. "
                 "Max Sharpe = miglior rendimento/rischio storico. Max rendimento = solo rendimento.")
        obiettivo = OBIETTIVI[scelta]
        long_only = col_lo.checkbox("Solo posizioni long (pesi ≥ 0)", value=True,
                                    help="Lascia attivo: niente vendite allo scoperto.")
        if obiettivo in ("max_sharpe", "max_ret"):
            st.warning(
                "⚠️ «Massimo Sharpe» e «Massimo rendimento» sono **backward-looking**: si "
                "**sovra-adattano allo storico** (overfitting) e tendono a **concentrare** il "
                "portafoglio su pochi asset che sono andati bene in passato — cosa che non si ripete "
                "uguale. Per il **lungo periodo** sono di solito più robuste **Minima varianza** o "
                "**Risk parity**."
            )
        if obiettivo == "max_decorr":
            st.info(
                "La **massima diversificazione** sceglie i pesi che sfruttano meglio la "
                "**decorrelazione** tra gli asset: massimizza il «diversification ratio» = media "
                "(pesata) delle volatilità dei singoli **÷** volatilità del portafoglio. Tende a "
                "distribuire su asset **poco correlati**. ⚠️ Si basa sulle **correlazioni storiche**, "
                "che possono cambiare nel tempo."
            )
        if not mtr.SCIPY_DISPONIBILE:
            st.caption("scipy non disponibile: si usano soluzioni analitiche (possono dare pesi negativi).")

        n_asset = len(tickers_ok)
        if long_only:
            alpha_perc = st.slider(
                "Quota minima per asset (% della quota equipesata)",
                min_value=0, max_value=100, value=25, step=5,
                help="0% = nessun vincolo (un asset può andare a 0). 100% = tutti equipesati.",
            )
            frazione_minima = alpha_perc / 100.0
            quota_equa = 1.0 / n_asset
            soglia_assoluta = frazione_minima * quota_equa
            st.caption(
                f"Con {n_asset} asset la quota equipesata è {quota_equa:.1%}: ogni asset peserà "
                f"**almeno {soglia_assoluta:.1%}** (e **al massimo {1 - (n_asset - 1) * soglia_assoluta:.1%}**)."
            )
            cap_min = max(5, -(-100 // n_asset))  # ceil(100/n): cap minimo ammissibile
            cap_perc = st.slider(
                "Cap massimo per asset (%)", min_value=int(cap_min), max_value=100, value=100, step=5,
                help="Tetto al peso di ogni singolo asset, per non concentrare troppo. 100% = nessun tetto.")
            peso_max = cap_perc / 100.0
        else:
            frazione_minima = 0.0
            peso_max = 1.0
            st.caption("Quota minima e cap per asset si applicano solo in modalità long-only.")

        w_opt = mtr.pesi_ottimizzati(rendimenti, obiettivo, risk_free, long_only, frazione_minima, peso_max)
        met_opt = mtr.metriche_portafoglio(rendimenti, w_opt, risk_free)

        if obiettivo == "max_ret" and long_only:
            if frazione_minima <= 0:
                st.warning(
                    "Con soli pesi long e nessuna quota minima, il **massimo rendimento** concentra "
                    "tutto sull'asset col rendimento storico più alto. Alza la quota minima per distribuirlo."
                )
            else:
                st.info(
                    "Il **massimo rendimento** assegna la quota minima a ogni asset e il resto all'asset "
                    "col rendimento storico più alto. Massimizza il rendimento passato, non riduce il rischio."
                )

        col_pesi, col_conf = st.columns([1, 1])
        with col_pesi:
            st.markdown("**Pesi ottimali**")
            st.dataframe(
                w_opt.rename(index=nomi).to_frame("Peso ottimale").style.format({"Peso ottimale": "{:.2%}"}),
                width="stretch",
            )
            st.button(
                "📌 Applica questi pesi al portafoglio",
                on_click=cm.cb_applica_pesi, args=(dict(w_opt),), width="stretch",
                help="Sostituisce i pesi attuali con quelli ottimali.",
            )
        with col_conf:
            st.markdown("**Confronto: portafoglio attuale vs ottimale**")
            confronto = pd.DataFrame(
                {
                    "Attuale": [met_pf["Rend. annuo (CAGR)"], met_pf["Volatilità annua (covarianza)"],
                                met_pf["Sharpe"], met_pf["Sortino"], met_pf["Max drawdown"]],
                    "Ottimale": [met_opt["Rend. annuo (CAGR)"], met_opt["Volatilità annua (covarianza)"],
                                 met_opt["Sharpe"], met_opt["Sortino"], met_opt["Max drawdown"]],
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
            front = mtr.frontiera_efficiente(rendimenti, n_punti=40, long_only=long_only, frazione_minima=frazione_minima, peso_max=peso_max)
            if not front.empty:
                fig_f = go.Figure()
                fig_f.add_trace(go.Scatter(x=front["vol"], y=front["rend"], mode="lines", name="Frontiera"))
                mu_asset = rendimenti.mean() * mtr.GIORNI_BORSA
                vol_asset = rendimenti.std(ddof=1) * (mtr.GIORNI_BORSA ** 0.5)
                fig_f.add_trace(go.Scatter(
                    x=vol_asset.values, y=mu_asset.values, mode="markers+text",
                    text=[nomi_corti[t] for t in rendimenti.columns], textposition="top center", name="Asset",
                ))
                fig_f.add_trace(go.Scatter(
                    x=[met_pf["Volatilità annua (covarianza)"]], y=[met_pf["Rend. annuo (CAGR)"]],
                    mode="markers", marker=dict(size=13, symbol="diamond", color="gray"), name="Portafoglio attuale",
                ))
                fig_f.add_trace(go.Scatter(
                    x=[met_opt["Volatilità annua (covarianza)"]], y=[met_opt["Rend. annuo (CAGR)"]],
                    mode="markers", marker=dict(size=16, symbol="star", color="green"),
                    name=f"Ottimale ({scelta.split('(')[0].strip()})",
                ))
                fig_f.update_layout(xaxis_title="Volatilità annua", yaxis_title="Rendimento medio annuo", hovermode="closest")
                fig_f.update_xaxes(tickformat=".0%")
                fig_f.update_yaxes(tickformat=".0%")
                st.plotly_chart(fig_f, width="stretch")
                st.caption(
                    "Cosa significa per te: la curva è il miglior rendimento ottenibile storicamente per "
                    "ogni livello di rischio. A parità di rischio, conviene stare il più **in alto** "
                    "possibile (più rendimento). ⚠️ È basata sul passato."
                )
            else:
                st.caption("Impossibile calcolare la frontiera per questo insieme di asset.")
        else:
            st.caption("Installa scipy per visualizzare la frontiera efficiente.")

# === Confronto con indici e portafogli famosi =============================
if sezione == "🆚 Confronto":
    st.subheader("Confronto con indici e portafogli famosi")
    st.caption(
        "Confronta l'andamento del **tuo** portafoglio con singoli ETF/indici e con allocazioni "
        "celebri. Le serie sono allineate sul periodo comune e "
        + ("convertite in " + ss.valuta_base + "." if ss.converti else "lasciate nella valuta nativa.")
    )

    famosi_sel = st.multiselect(
        "Portafogli famosi da confrontare",
        list(cm.PORTAFOGLI_FAMOSI.keys()),
        default=["60/40 (azioni/obbligazioni)", "All Weather (Ray Dalio)"],
    )
    txt_bench = st.text_input(
        "Altri ticker/indici da confrontare (separati da virgola)",
        value="",
        placeholder="es. CSPX.MI, ^GSPC, SWDA.MI",
    )
    bench_tickers = [t.strip().upper() for t in txt_bench.replace(";", ",").split(",") if t.strip()]

    serie_dict = {"Il mio portafoglio": mtr.serie_rendimenti_portafoglio(rendimenti, pesi)}
    note = []
    with st.spinner("Scarico i dati per il confronto..."):
        for nome in famosi_sel:
            s, mancanti = cm.rendimenti_portafoglio_famoso(
                nome, ss.period, ss.data_inizio, ss.data_fine, ss.valuta_base, ss.converti
            )
            if not s.empty:
                serie_dict[nome] = s
                if mancanti:
                    note.append(f"{nome}: proxy mancanti ({', '.join(mancanti)}), riallocato sui presenti.")
            else:
                note.append(f"{nome}: dati non disponibili.")
        for t in bench_tickers:
            ris_b = cm.carica_dati((t,), ss.period, ss.data_inizio, ss.data_fine, ss.valuta_base, ss.converti)
            if not ris_b.prezzi.empty:
                nome_b = cm.nomi_di((t,)).get(t, t)
                serie_dict[nome_b] = mtr.rendimenti_giornalieri(ris_b.prezzi).iloc[:, 0]
            else:
                note.append(f"{t}: dati non disponibili.")

    for n in note:
        st.warning(n)

    df_rend = pd.DataFrame(serie_dict).dropna()
    if df_rend.shape[1] < 2 or df_rend.empty:
        st.info("Aggiungi almeno un portafoglio famoso o un ticker per fare il confronto.")
    else:
        st.caption(
            f"Periodo comune: {df_rend.index.min():%d/%m/%Y} → {df_rend.index.max():%d/%m/%Y} "
            f"({len(df_rend)} sedute). Tutte le curve partono da 100 alla prima data comune."
        )
        cum = mtr.serie_cumulata(df_rend, base=100.0)
        fig_conf = px.line(cum, labels={"value": "Indice (base 100)", "index": "Data", "variable": "Serie"})
        fig_conf.update_traces(line=dict(width=1.4))
        fig_conf.update_traces(selector=dict(name="Il mio portafoglio"), line=dict(width=3.6, color="black"))
        fig_conf.update_layout(hovermode="x unified", legend_title_text="Serie")
        st.plotly_chart(fig_conf, width="stretch")

        st.markdown("**Statistiche a confronto** (sul periodo comune)")
        met_conf = mtr.metriche_asset(df_rend, risk_free)
        st.dataframe(cm.formatta_metriche(met_conf), width="stretch")
        st.caption(
            "I portafogli famosi sono ricostruiti con ETF rappresentativi (USA): possono differire "
            "leggermente dalle versioni «originali». ⚠️ Analisi storica a scopo didattico, "
            "non un consiglio di investimento."
        )

# === Assistente guidato (senza AI esterna, nessuna chiave) =================
if sezione == "🤖 Assistente":
    st.subheader("🤖 Assistente")
    st.caption(
        "ℹ️ Ti spiego l'app e i **tuoi numeri** a scopo **didattico**. Non do consigli di "
        "investimento. (Gratuito, nessun account: rispondo usando i dati già calcolati.)"
    )

    # Contesto per le risposte: numeri già calcolati + diversificazione geo/settore.
    comp_eff_a = cm.composizione_effettiva(tickers_ok)
    div_paese = mtr.indice_diversificazione(mtr.aggrega_composizione(pesi, comp_eff_a, "paese")[0])
    div_settore = mtr.indice_diversificazione(mtr.aggrega_composizione(pesi, comp_eff_a, "settore")[0])
    rc_ass = mtr.contributo_rischio(rendimenti, pesi)
    if len(rc_ass) and "Contributo %" in rc_ass:
        _top_t = rc_ass["Contributo %"].idxmax()
        top_rischio_nome = nomi.get(_top_t, _top_t)
        top_rischio_quota = float(rc_ass["Contributo %"].max())
    else:
        top_rischio_nome, top_rischio_quota = None, None

    dati_ass = {
        "met_pf": met_pf,
        "riep": riep,
        "n_asset": len(tickers_ok),
        "div_paese": div_paese,
        "div_settore": div_settore,
        "top_rischio_nome": top_rischio_nome,
        "top_rischio_quota": top_rischio_quota,
    }

    # Cronologia della conversazione (in session_state).
    if "chat_ass" not in ss:
        ss.chat_ass = [(
            "assistant",
            "Ciao! 👋 Sono il tuo assistente. Posso spiegarti l'app e i **tuoi numeri** "
            "(rischio, diversificazione, Sharpe…). Scegli una domanda rapida o scrivimi sotto.",
        )]

    # Domande rapide (pulsanti).
    st.markdown("**Domande rapide:**")
    suggerite = [
        "Quanto sono diversificato?",
        "Com'è il mio rischio?",
        "Cosa significa Sharpe?",
        "Quale asset pesa di più sul rischio?",
        "Come funziona l'app?",
        "Cosa significa il max drawdown?",
    ]
    cols_s = st.columns(2)
    for _i, _q in enumerate(suggerite):
        if cols_s[_i % 2].button(_q, key=f"sugg_{_i}", width="stretch"):
            ss.chat_ass.append(("user", _q))
            ss.chat_ass.append(("assistant", cm.risposta_assistente(_q, dati_ass)))

    # Input libero.
    _libera = st.chat_input("Scrivi una domanda… (es. «cos'è il drawdown?»)")
    if _libera:
        ss.chat_ass.append(("user", _libera))
        ss.chat_ass.append(("assistant", cm.risposta_assistente(_libera, dati_ass)))

    # Pulisci (prima del rendering, così l'effetto è immediato).
    if len(ss.chat_ass) > 1 and st.button("🧹 Pulisci conversazione"):
        ss.chat_ass = [("assistant", "Conversazione azzerata. Chiedimi pure! 🙂")]

    # Conversazione.
    for _ruolo, _testo in ss.chat_ass:
        with st.chat_message(_ruolo, avatar="🤖" if _ruolo == "assistant" else "🧑"):
            st.markdown(_testo)

# A3 — footer disclaimer persistente (sotto qualunque sezione attiva).
cm.mostra_footer_disclaimer()
