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

    # Portafogli "pronti" da caricare con un clic.
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
        col1.markdown(f"**{nome}**  \n`{t}`")
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

(tab_asset, tab_pf, tab_alloc, tab_timing, tab_pac, tab_obiettivo, tab_costi, tab_rib,
 tab_stat, tab_opt, tab_conf) = st.tabs(
    ["📈 Singoli asset", "💼 Portafoglio", "🌍 Allocazione", "⏱️ Timing", "💶 PAC", "🎯 Obiettivo",
     "💰 Costi e tasse", "♻️ Ribilanciamento", "📊 Statistica", "🧮 Ottimizzazione", "🆚 Confronto"]
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

    st.subheader("Portafoglio vs singoli asset (base 100)")
    serie_pf = mtr.serie_rendimenti_portafoglio(rendimenti, pesi)
    cum_all = mtr.serie_cumulata(rendimenti, base=100.0).rename(columns=nomi_corti)
    cum_all["PORTAFOGLIO"] = mtr.serie_cumulata(serie_pf, base=100.0)
    fig_cmp = px.line(cum_all, labels={"value": "Indice (base 100)", "index": "Data", "variable": "Serie"})
    fig_cmp.update_traces(line=dict(width=1.2))
    fig_cmp.update_traces(selector=dict(name="PORTAFOGLIO"), line=dict(width=3.5, color="black"))
    fig_cmp.update_layout(hovermode="x unified")
    st.plotly_chart(fig_cmp, width="stretch")

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
        st.plotly_chart(fig_corr, width="stretch")
        st.caption(
            "Valori vicini a 1 = molto correlati (poca diversificazione); "
            "vicini a 0 o negativi = scorrelati (maggiore diversificazione)."
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

    st.divider()
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
                f"{len(roll)} possibili giorni di partenza analizzati su ~{anni_storico:.1f} anni di storico. "
                "⚠️ I rendimenti passati non garantiscono quelli futuri."
            )

# === PAC / DCA (backtest storico) =========================================
with tab_pac:
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
with tab_obiettivo:
    st.subheader("Proiezione a obiettivo")
    st.caption(
        "Quanto dovresti versare ogni mese per raggiungere una certa cifra, usando rendimento e "
        "volatilità **storici** del tuo portafoglio. Stima statistica con scenari, non una garanzia."
    )
    co1, co2 = st.columns(2)
    obiettivo_eur = co1.number_input(
        "Obiettivo (€)", min_value=1000.0, value=100000.0, step=1000.0,
        help="La cifra che vorresti raggiungere.",
    )
    co2.metric("Orizzonte", f"{orizzonte} anni", help="Si imposta nella barra laterale.")

    with st.spinner("Simulo gli scenari..."):
        ris_obj = cm.carica_dati(tuple(tickers_ok), "max", None, None, ss.valuta_base, ss.converti)
    if ris_obj.prezzi.empty:
        st.warning("Storico non disponibile per il calcolo.")
    else:
        serie_pf_obj = mtr.serie_rendimenti_portafoglio(mtr.rendimenti_giornalieri(ris_obj.prezzi), pesi)
        mu = mtr.cagr(serie_pf_obj)
        sigma = mtr.volatilita_annua(serie_pf_obj)
        st.caption(f"Ipotesi dal tuo portafoglio: rendimento storico **{mu:.1%}/anno**, volatilità **{sigma:.1%}**.")
        proj = mtr.proiezione_obiettivo(mu, sigma, obiettivo_eur, orizzonte)
        if proj is None:
            st.warning("Parametri non validi.")
        else:
            val = ss.valuta_base if ss.converti else ""
            st.metric(
                "Versamento mensile necessario (stima)", f"{proj['pmt_mensile']:,.0f} {val}",
                help="Quanto versare ogni mese per centrare l'obiettivo nello scenario medio.",
            )
            sc1, sc2, sc3 = st.columns(3)
            sc1.metric("Scenario pessimista", f"{proj['pessimista']:,.0f} {val}",
                       help="Tra i casi peggiori (10° percentile delle simulazioni).")
            sc2.metric("Scenario medio", f"{proj['medio']:,.0f} {val}", help="Il caso centrale (50%).")
            sc3.metric("Scenario ottimista", f"{proj['ottimista']:,.0f} {val}",
                       help="Tra i casi migliori (90° percentile delle simulazioni).")
            st.caption(f"Probabilità stimata di raggiungere l'obiettivo con quel versamento: **{proj['prob_obiettivo']:.0%}**.")
            bande = proj["bande"].copy()
            bande.index = bande.index / 12.0
            fig_obj = px.line(bande, labels={"value": f"Valore ({val})", "index": "Anni", "variable": ""})
            fig_obj.add_hline(y=obiettivo_eur, line_dash="dot", line_color="green", annotation_text="obiettivo")
            fig_obj.update_layout(hovermode="x unified", legend_title_text="")
            st.plotly_chart(fig_obj, width="stretch")
            st.caption("⚠️ Simulazione statistica (Monte Carlo) su ipotesi storiche: il futuro può essere diverso.")

# === Costi (TER) e fiscalità ==============================================
with tab_costi:
    st.subheader("Costi (TER) e fiscalità — stime didattiche")
    st.caption(
        "Inserisci il **TER** (costo annuo dell'ETF) e l'**aliquota** fiscale di ogni asset. "
        "In Italia: **26%** in generale, **12,5%** sui titoli di Stato/white-list; **bollo 0,2%/anno**."
    )
    righe_costi = []
    for t in tickers_ok:
        c = ss.costi.get(t, {})
        righe_costi.append({"Ticker": t, "Asset": nomi.get(t, t),
                            "TER %": float(c.get("ter", 0.20)),
                            "Aliquota %": float(c.get("aliquota", 26.0))})
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
    st.caption("⚠️ Stima didattica: la fiscalità reale dipende dallo strumento e dalla normativa vigente.")

# === Ribilanciamento vs buy & hold ========================================
with tab_rib:
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
            met_rib = mtr.metriche_asset(mtr.rendimenti_giornalieri(serie_rib), risk_free)
            st.dataframe(cm.formatta_metriche(met_rib), width="stretch")
            st.caption(
                f"Numero di ribilanci: **{res_rib['n_ribilanci']}**. "
                "⚠️ Non sono inclusi costi di transazione o tasse sui ribilanci (analisi didattica)."
            )

# === Lettura statistica del portafoglio ===================================
with tab_stat:
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
with tab_opt:
    st.subheader("Ottimizzazione del portafoglio")
    if len(tickers_ok) < 2:
        st.info("Servono almeno 2 asset per l'ottimizzazione.")
    else:
        OBIETTIVI = {
            "Minima varianza (minimo rischio)": "min_var",
            "Risk parity (parità di rischio)": "risk_parity",
            "Massimo indice di Sharpe (tangenza)": "max_sharpe",
            "Massimo rendimento annuo": "max_ret",
        }
        col_ob, col_lo = st.columns([2, 1])
        scelta = col_ob.selectbox(
            "Obiettivo", list(OBIETTIVI.keys()), index=0,
            help="Minima varianza = minor rischio. Risk parity = ogni asset contribuisce ugualmente "
                 "al rischio. Max Sharpe = miglior rendimento/rischio storico. Max rendimento = solo rendimento.")
        obiettivo = OBIETTIVI[scelta]
        long_only = col_lo.checkbox("Solo posizioni long (pesi ≥ 0)", value=True,
                                    help="Lascia attivo: niente vendite allo scoperto.")
        if obiettivo in ("max_sharpe", "max_ret"):
            st.warning(
                "ℹ️ «Massimo Sharpe» e «Massimo rendimento» guardano **solo al passato** e tendono a "
                "**concentrare** su pochi asset: il passato non si ripete uguale. Per un portafoglio più "
                "equilibrato valuta **Minima varianza** o **Risk parity**."
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
            else:
                st.caption("Impossibile calcolare la frontiera per questo insieme di asset.")
        else:
            st.caption("Installa scipy per visualizzare la frontiera efficiente.")

# === Confronto con indici e portafogli famosi =============================
with tab_conf:
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
