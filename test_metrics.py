"""Controlli rapidi sui calcoli di metrics.py e dataset_composizioni.py.

Avvio:  python test_metrics.py   (nessuna rete, nessuno Streamlit)
"""
import numpy as np
import pandas as pd

import dataset_composizioni as dsc
import metrics as mtr

rng = np.random.default_rng(0)
date = pd.bdate_range("2020-01-01", periods=1000)
rend = pd.DataFrame(
    rng.normal([0.0004, 0.0003, 0.0001], [0.012, 0.015, 0.004], size=(1000, 3)),
    index=date, columns=["A", "B", "C"],
)

# 1) Il portafoglio «massimo Sharpe» ha davvero lo Sharpe mostrato più alto.
rf = 0.02
w_max = mtr.pesi_massimo_sharpe(rend, rf)
s_max = mtr.sharpe(mtr.serie_rendimenti_portafoglio(rend, w_max), rf)
for w in [np.full(3, 1 / 3)] + list(rng.dirichlet(np.ones(3), 100)):
    s = mtr.sharpe(mtr.serie_rendimenti_portafoglio(rend, pd.Series(w, index=rend.columns)), rf)
    assert s_max >= s - 1e-4, (s_max, s, w)

# 2) Risk-free costante o come serie storica (mensile) danno lo stesso risultato.
rf_serie = pd.Series(0.03, index=pd.date_range("2019-01-01", "2024-12-01", freq="MS"))
r = rend["A"]
assert abs(mtr.sharpe(r, 0.03) - mtr.sharpe(r, rf_serie)) < 1e-12
assert abs(mtr.sortino(r, 0.03) - mtr.sortino(r, rf_serie)) < 1e-12

# 3) Inflazione media: indice da 100 a 121 in 2 anni ≈ 10%/anno.
hicp = pd.Series(np.linspace(100, 121, 25), index=pd.date_range("2020-01-01", periods=25, freq="MS"))
assert abs(mtr.inflazione_annua_media(hicp, "2020-01-15", "2022-01-20") - 0.10) < 1e-3
assert np.isnan(mtr.inflazione_annua_media(hicp, "2010-01-01", "2022-01-01"))  # fuori copertura

# 4) Aliquota pro-quota sui titoli di Stato.
assert dsc.aliquota_default("SWDA.MI") == 26.0
assert dsc.aliquota_default("AGGH.MI") == 18.6
assert dsc.aliquota_default("XGLE.MI") == 12.5

# 5) Obiettivo: con mesi storici tutti uguali la simulazione è deterministica,
#    e il valore netto (dopo tasse sul guadagno) coincide esattamente con l'obiettivo.
mesi = pd.Series(0.01, index=range(24))
p = mtr.proiezione_obiettivo(mesi, 0.06, 100_000, 10, 0.75, aliquota=0.26)
m = 1.06 ** (1 / 12) - 1
lordo = sum((1 + m) ** k for k in range(1, 121))                 # 1 €/mese per 120 mesi
atteso_pmt = 100_000 / (lordo - 0.26 * (lordo - 120))
assert abs(p["pmt_mensile"] - atteso_pmt) < 1e-6 * atteso_pmt
assert abs(p["medio"] - 100_000) < 1e-3 and p["prob_effettiva"] == 1.0
assert mtr.proiezione_obiettivo(mesi.iloc[:6], 0.06, 100_000, 10) is None  # storico troppo corto

# 6) Correlazioni settimanali: uno sfasamento di UN giorno azzera la correlazione
#    giornaliera ma non quella settimanale.
a = rend["A"]
sfasati = pd.DataFrame({"a": a, "b": a.shift(1)}).dropna()
assert abs(sfasati.corr().iloc[0, 1]) < 0.1
assert mtr.matrice_correlazione(sfasati).iloc[0, 1] > 0.6

# 7) Backtest semaforo: su un mercato in crescita costante e calmo resta sempre investito.
prezzo = pd.Series(100 * np.exp(np.cumsum(0.0005 + rng.normal(0, 0.001, 1500))),
                   index=pd.bdate_range("2015-01-01", periods=1500))
bt = mtr.backtest_semaforo(prezzo)
assert bt["valido"] and bt["cambi"] == 0 and abs(bt["cagr_strat"] - bt["cagr_bh"]) < 1e-12

print("OK - tutti i controlli superati")
