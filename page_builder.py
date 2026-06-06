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
import metrics as mtr

ss = st.session_state

st.header("🧱 Builder — Costruzione e analisi del portafoglio")

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
            rc1.markdown(
                f"**{r['nome']}**  \n`{r['symbol']}` · {r['tipo'] or 'n/d'} · {r['borsa'] or 'n/d'}"
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

    sel = cm.portafoglio_pulito()
    if sel.empty:
        st.info("Nessun asset selezionato. Usa la ricerca qui sopra per aggiungerne.")
        st.stop()

    h1, h2, h3 = st.columns([6, 2, 1])
    h1.markdown("**Asset**")
    h2.markdown("**Peso %**")
    h3.markdown("**Rimuovi**")

    pesi_correnti = {}
    for _, riga in sel.iterrows():
        t = riga["Ticker"]
        nome = riga["Nome"]
        if f"w_{t}" not in ss:
            ss[f"w_{t}"] = float(riga["Peso %"]) if pd.notna(riga["Peso %"]) else 0.0
        col1, col2, col3 = st.columns([6, 2, 1])
        col1.markdown(f"**{nome}**  \n`{t}`")
        col2.number_input("Peso %", min_value=0.0, step=1.0, key=f"w_{t}", label_visibility="collapsed")
        col3.button("🗑", key=f"del_{t}", on_click=cm.cb_rimuovi, args=(t,))
        pesi_correnti[t] = ss[f"w_{t}"]

    ss.selezionati = sel.assign(**{"Peso %": [pesi_correnti[t] for t in sel["Ticker"]]})

    azione1, azione2, azione3 = st.columns([1, 1, 2])
    azione1.button("⚖️ Equipesati", on_click=cm.cb_equipesati, width="stretch")
    azione2.button("🧹 Svuota", on_click=cm.cb_svuota, width="stretch")
    tot = sum(pesi_correnti.values())
    azione3.metric("Somma pesi", f"{tot:.1f}%", help="I pesi vengono normalizzati a 100% per i calcoli.")

tickers = sel["Ticker"].tolist()
pesi_input = pd.Series([pesi_correnti[t] for t in tickers], index=tickers)

# ---------------------------------------------------------------------------
# Download dati e calcoli
# ---------------------------------------------------------------------------

with st.spinner("Scarico i dati da Yahoo Finance..."):
    ris = cm.carica_dati(
        tuple(tickers), ss.period, ss.data_inizio, ss.data_fine, ss.valuta_base, ss.converti
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
risk_free = ss.risk_free

nomi = {t: ss.selezionati.set_index("Ticker")["Nome"].get(t, t) for t in tickers_ok}
nomi_corti = {t: cm.etichetta_corta(nomi[t]) for t in tickers_ok}

col1, col2, col3 = st.columns(3)
col1.metric("Asset analizzati", len(tickers_ok))
col2.metric("Periodo", f"{prezzi.index.min():%d/%m/%Y} → {prezzi.index.max():%d/%m/%Y}")
col3.metric("Valuta", ss.valuta_base if ss.converti else "nativa (mista)")
if ris.valute:
    valute_txt = ", ".join(f"{nomi.get(t, t)}: {c}" for t, c in ris.valute.items())
    st.caption(f"Valute native rilevate — {valute_txt}")

# ---------------------------------------------------------------------------
# Tab di analisi del portafoglio
# ---------------------------------------------------------------------------

tab_asset, tab_pf, tab_alloc, tab_timing, tab_opt = st.tabs(
    ["📈 Singoli asset", "💼 Portafoglio", "🌍 Allocazione", "⏱️ Timing", "🧮 Ottimizzazione"]
)

# === Singoli asset =========================================================
with tab_asset:
    st.subheader("Metriche per singolo asset")
    met_asset = mtr.metriche_asset(rendimenti, risk_free).rename(index=nomi)
    st.dataframe(cm.formatta_metriche(met_asset), width="stretch")

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

# === Portafoglio ===========================================================
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
        fig_corr = px.imshow(corr, text_auto=".2f", color_continuous_scale="RdBu_r", zmin=-1, zmax=1, aspect="auto")
        st.plotly_chart(fig_corr, width="stretch")
        st.caption(
            "Valori vicini a 1 = molto correlati (poca diversificazione); "
            "vicini a 0 o negativi = scorrelati (maggiore diversificazione)."
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
            "Quanto ciascun asset contribuisce alla volatilità totale. "
            "Confronta col peso: chi contribuisce meno del proprio peso diversifica."
        )
        st.dataframe(
            rc.style.format(
                {"Peso": "{:.2%}", "Contributo marginale": "{:.4f}",
                 "Contributo assoluto": "{:.4f}", "Contributo %": "{:.2%}"}
            ),
            width="stretch",
        )

# === Allocazione ===========================================================
with tab_alloc:
    st.subheader("Composizione per paese e settore")
    st.info(
        "La composizione (holdings) **non** si ricava dai prezzi. Si può provare a recuperare i "
        "settori da yfinance (spesso assenti per ETF UCITS europei) e/o inserirla a mano qui sotto "
        "o da CSV. Le righe sono identificate dal **ticker**."
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

# === Timing (rolling returns) =============================================
with tab_timing:
    st.subheader("Quanto avrebbe reso, a seconda di quando avresti investito")
    st.caption(
        "Ogni punto risponde a: «se avessi investito in **questo** giorno e tenuto il "
        "portafoglio per la finestra scelta, quanto avrei guadagnato **in media all'anno**?». "
        "Serve a capire quanto conta il *momento* in cui si entra. Usa **tutto** lo storico "
        "disponibile (non l'intervallo nella barra laterale)."
    )

    FINESTRE = {"1 anno": 1, "3 anni": 3, "5 anni": 5, "10 anni": 10}
    scelta_fin = st.radio("Finestra di investimento", list(FINESTRE.keys()), index=2, horizontal=True)
    anni_fin = FINESTRE[scelta_fin]

    # Scarica tutto lo storico comune disponibile per il portafoglio.
    with st.spinner("Calcolo i rendimenti su tutto lo storico..."):
        ris_max = cm.carica_dati(tuple(tickers_ok), "max", None, None, ss.valuta_base, ss.converti)

    if ris_max.prezzi.empty:
        st.warning("Storico non disponibile per il calcolo.")
    else:
        rend_max = mtr.rendimenti_giornalieri(ris_max.prezzi)
        serie_pf_max = mtr.serie_rendimenti_portafoglio(rend_max, pesi)
        roll = mtr.rolling_rendimenti_annualizzati(serie_pf_max, anni_fin)

        anni_storico = (ris_max.prezzi.index.max() - ris_max.prezzi.index.min()).days / 365.25
        if roll.empty:
            st.warning(
                f"Storico insufficiente: servono più di **{anni_fin} anni** di dati comuni a tutti "
                f"gli asset, ma ne risultano circa **{anni_storico:.1f}**. Prova una finestra più corta "
                "(es. 1 o 3 anni) o asset con storia più lunga."
            )
        else:
            # Statistiche di sintesi.
            peggiore, mediana, migliore = roll.min(), roll.median(), roll.max()
            quota_pos = (roll > 0).mean()
            s1, s2, s3, s4 = st.columns(4)
            s1.metric("Peggiore", f"{peggiore:.2%}/anno")
            s2.metric("Mediana", f"{mediana:.2%}/anno")
            s3.metric("Migliore", f"{migliore:.2%}/anno")
            s4.metric("Finestre positive", f"{quota_pos:.0%}", help="Quota di giorni di partenza che hanno dato un rendimento > 0.")

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
                f"{len(roll)} possibili giorni di partenza analizzati su ~{anni_storico:.1f} anni di storico. "
                "⚠️ I rendimenti passati non garantiscono quelli futuri."
            )

# === Ottimizzazione ========================================================
with tab_opt:
    st.subheader("Ottimizzazione del portafoglio")
    if len(tickers_ok) < 2:
        st.info("Servono almeno 2 asset per l'ottimizzazione.")
    else:
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
        else:
            frazione_minima = 0.0
            st.caption("Quota minima per asset disattivata: si applica solo in modalità long-only.")

        w_opt = mtr.pesi_ottimizzati(rendimenti, obiettivo, risk_free, long_only, frazione_minima)
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
            front = mtr.frontiera_efficiente(rendimenti, n_punti=40, long_only=long_only, frazione_minima=frazione_minima)
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
            else:
                st.caption("Impossibile calcolare la frontiera per questo insieme di asset.")
        else:
            st.caption("Installa scipy per visualizzare la frontiera efficiente.")
