"""
metrics.py
==========
Calcoli finanziari su prezzi e rendimenti di ETF / indici.

Convenzioni adottate in tutto il modulo:
- si lavora sui **rendimenti giornalieri semplici** (variazione percentuale);
- si annualizza con **252** giorni di borsa;
- il rendimento annualizzato è il **CAGR geometrico** (non la media aritmetica);
- per la volatilità si usa la deviazione standard campionaria (``ddof=1``);
- i pesi del portafoglio vengono sempre normalizzati a somma 1.

Le metriche di portafoglio sono calcolate, dove possibile, sulla serie dei
rendimenti del portafoglio (somma pesata dei rendimenti dei singoli asset),
così risultano coerenti tra loro. La sola eccezione "voluta" è la volatilità
di portafoglio, calcolata anche con la matrice di covarianza (come richiesto):
σ_p = √(wᵀ Σ w) con Σ annualizzata.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

# Numero convenzionale di giorni di borsa in un anno.
GIORNI_BORSA = 252

# scipy serve solo per gli "extra" (minima varianza vincolata, frontiera).
# Se non è installato, le funzioni di ottimizzazione hanno comunque un
# fallback analitico (non vincolato).
try:  # pragma: no cover - dipende dall'ambiente
    from scipy.optimize import minimize

    SCIPY_DISPONIBILE = True
except Exception:  # pragma: no cover
    SCIPY_DISPONIBILE = False


# ---------------------------------------------------------------------------
# Funzioni di base sui rendimenti
# ---------------------------------------------------------------------------

def rendimenti_giornalieri(prezzi: pd.DataFrame) -> pd.DataFrame:
    """Calcola i rendimenti giornalieri semplici dai prezzi.

    La prima riga (NaN per costruzione) viene eliminata.
    """
    return prezzi.pct_change().dropna(how="all")


def normalizza_pesi(pesi: dict[str, float] | pd.Series, colonne: list[str]) -> pd.Series:
    """Restituisce i pesi nell'ordine di ``colonne``, normalizzati a somma 1.

    I ticker assenti dai pesi ricevono peso 0. Se la somma è nulla si
    sollevano i pesi a equipesati per evitare divisioni per zero.
    """
    if isinstance(pesi, dict):
        pesi = pd.Series(pesi, dtype="float64")
    pesi = pesi.reindex(colonne).fillna(0.0).astype("float64")
    somma = pesi.sum()
    if somma == 0:
        return pd.Series(1.0 / len(colonne), index=colonne)
    return pesi / somma


# ---------------------------------------------------------------------------
# Metriche per singolo asset (e riutilizzabili su una serie qualsiasi)
# ---------------------------------------------------------------------------

def cagr(rendimenti: pd.Series) -> float:
    """Rendimento annualizzato geometrico (CAGR) da una serie di rendimenti."""
    rendimenti = rendimenti.dropna()
    n = len(rendimenti)
    if n == 0:
        return np.nan
    crescita_totale = float((1.0 + rendimenti).prod())
    if crescita_totale <= 0:
        return -1.0  # capitale azzerato
    return crescita_totale ** (GIORNI_BORSA / n) - 1.0


def volatilita_annua(rendimenti: pd.Series) -> float:
    """Volatilità annualizzata = dev. std giornaliera × √252."""
    rendimenti = rendimenti.dropna()
    if len(rendimenti) < 2:
        return np.nan
    return float(rendimenti.std(ddof=1) * np.sqrt(GIORNI_BORSA))


def downside_deviation_annua(rendimenti: pd.Series, mar_annuo: float = 0.0) -> float:
    """Downside deviation annualizzata rispetto a un MAR (rendimento minimo).

    Si considerano solo i rendimenti sotto il MAR giornaliero; gli altri
    contribuiscono 0 (ma restano nel denominatore: definizione standard).
    """
    rendimenti = rendimenti.dropna()
    if len(rendimenti) == 0:
        return np.nan
    mar_giornaliero = mar_annuo / GIORNI_BORSA
    sotto = (rendimenti - mar_giornaliero).clip(upper=0.0)
    dd_giornaliera = np.sqrt((sotto ** 2).mean())
    return float(dd_giornaliera * np.sqrt(GIORNI_BORSA))


def sharpe(rendimenti: pd.Series, risk_free: float = 0.0) -> float:
    """Indice di Sharpe = (CAGR − risk_free) / volatilità annua."""
    vol = volatilita_annua(rendimenti)
    if vol is None or np.isnan(vol) or vol == 0:
        return np.nan
    return (cagr(rendimenti) - risk_free) / vol


def sortino(rendimenti: pd.Series, risk_free: float = 0.0) -> float:
    """Indice di Sortino = (CAGR − risk_free) / downside deviation annua.

    Il MAR usato per la downside deviation è il risk-free stesso.
    """
    dd = downside_deviation_annua(rendimenti, mar_annuo=risk_free)
    if dd is None or np.isnan(dd) or dd == 0:
        return np.nan
    return (cagr(rendimenti) - risk_free) / dd


def serie_drawdown(rendimenti: pd.Series) -> pd.Series:
    """Serie temporale del drawdown (distanza % dal massimo precedente)."""
    rendimenti = rendimenti.dropna()
    ricchezza = (1.0 + rendimenti).cumprod()
    picco = ricchezza.cummax()
    return ricchezza / picco - 1.0


def max_drawdown(rendimenti: pd.Series) -> float:
    """Massima perdita dal picco (valore negativo, es. -0.35 = −35%)."""
    dd = serie_drawdown(rendimenti)
    if dd.empty:
        return np.nan
    return float(dd.min())


def rendimento_cumulato(rendimenti: pd.Series) -> float:
    """Rendimento cumulato totale sul periodo (frazione, es. 0.8 = +80%)."""
    rendimenti = rendimenti.dropna()
    if len(rendimenti) == 0:
        return np.nan
    return float((1.0 + rendimenti).prod() - 1.0)


def serie_cumulata(rendimenti: pd.DataFrame | pd.Series, base: float = 100.0):
    """Indice della ricchezza normalizzato a ``base`` (default 100)."""
    return base * (1.0 + rendimenti).cumprod()


def metriche_asset(rendimenti: pd.DataFrame, risk_free: float = 0.0) -> pd.DataFrame:
    """Calcola tutte le metriche per ogni asset (una riga per ticker)."""
    righe = {}
    for ticker in rendimenti.columns:
        r = rendimenti[ticker].dropna()
        righe[ticker] = {
            "Rend. annuo (CAGR)": cagr(r),
            "Volatilità annua": volatilita_annua(r),
            "Sharpe": sharpe(r, risk_free),
            "Sortino": sortino(r, risk_free),
            "Max drawdown": max_drawdown(r),
            "Rend. cumulato": rendimento_cumulato(r),
        }
    return pd.DataFrame(righe).T


# ---------------------------------------------------------------------------
# Metriche di portafoglio
# ---------------------------------------------------------------------------

def serie_rendimenti_portafoglio(rendimenti: pd.DataFrame, pesi: pd.Series) -> pd.Series:
    """Serie dei rendimenti giornalieri del portafoglio (somma pesata).

    Nota: è un ribilanciamento giornaliero implicito ai pesi target, scelta
    standard e coerente con le metriche calcolate su questa serie.
    """
    pesi = normalizza_pesi(pesi, list(rendimenti.columns))
    return rendimenti.mul(pesi, axis=1).sum(axis=1)


def matrice_covarianza_annua(rendimenti: pd.DataFrame) -> pd.DataFrame:
    """Matrice di covarianza dei rendimenti, annualizzata (× 252)."""
    return rendimenti.cov() * GIORNI_BORSA


def volatilita_portafoglio_cov(rendimenti: pd.DataFrame, pesi: pd.Series) -> float:
    """Volatilità di portafoglio dalla covarianza: σ_p = √(wᵀ Σ w).

    Σ è la covarianza **annualizzata**. Questo è il modo corretto (tiene
    conto delle correlazioni), diverso dalla media pesata delle volatilità.
    """
    pesi = normalizza_pesi(pesi, list(rendimenti.columns))
    sigma = matrice_covarianza_annua(rendimenti)
    w = pesi.values
    var = float(w @ sigma.values @ w)
    return float(np.sqrt(max(var, 0.0)))


def matrice_correlazione(rendimenti: pd.DataFrame) -> pd.DataFrame:
    """Matrice di correlazione dei rendimenti tra gli asset."""
    return rendimenti.corr()


def contributo_rischio(rendimenti: pd.DataFrame, pesi: pd.Series) -> pd.DataFrame:
    """Contributo di ciascun asset alla volatilità totale del portafoglio.

    - contributo marginale (MCR) = (Σ w) / σ_p
    - contributo assoluto = w_i × MCR_i  (la somma è σ_p)
    - contributo % = contributo assoluto / σ_p  (la somma è 100%)

    Mostra chi *aggiunge* rischio e chi *diversifica* (un asset può avere
    peso alto ma contributo al rischio basso se poco correlato agli altri).
    """
    colonne = list(rendimenti.columns)
    pesi = normalizza_pesi(pesi, colonne)
    sigma = matrice_covarianza_annua(rendimenti)
    w = pesi.values

    sigma_p = float(np.sqrt(max(w @ sigma.values @ w, 0.0)))
    if sigma_p == 0:
        # Caso degenere: nessuna variabilità.
        zero = pd.Series(0.0, index=colonne)
        return pd.DataFrame(
            {
                "Peso": pesi,
                "Contributo marginale": zero,
                "Contributo assoluto": zero,
                "Contributo %": zero,
            }
        )

    mcr = sigma.values @ w / sigma_p          # contributo marginale al rischio
    contributo_assoluto = w * mcr             # somma = sigma_p
    contributo_pct = contributo_assoluto / sigma_p  # somma = 1

    return pd.DataFrame(
        {
            "Peso": pesi.values,
            "Contributo marginale": mcr,
            "Contributo assoluto": contributo_assoluto,
            "Contributo %": contributo_pct,
        },
        index=colonne,
    )


def metriche_portafoglio(
    rendimenti: pd.DataFrame, pesi: pd.Series, risk_free: float = 0.0
) -> dict[str, float]:
    """Riepilogo delle metriche di portafoglio in un dizionario.

    Tutte calcolate sulla serie dei rendimenti del portafoglio, tranne la
    volatilità (anche da covarianza). Le due volatilità coincidono a meno di
    differenze di campione: vengono restituite entrambe per trasparenza.
    """
    serie_pf = serie_rendimenti_portafoglio(rendimenti, pesi)
    return {
        "Rend. annuo (CAGR)": cagr(serie_pf),
        "Volatilità annua (serie)": volatilita_annua(serie_pf),
        "Volatilità annua (covarianza)": volatilita_portafoglio_cov(rendimenti, pesi),
        "Sharpe": sharpe(serie_pf, risk_free),
        "Sortino": sortino(serie_pf, risk_free),
        "Max drawdown": max_drawdown(serie_pf),
        "Rend. cumulato": rendimento_cumulato(serie_pf),
    }


def rolling_rendimenti_annualizzati(serie_rendimenti: pd.Series, anni: int) -> pd.Series:
    """Rendimento **annualizzato** per ogni possibile giorno di investimento.

    Per ciascuna data di partenza t calcola: se avessi investito quel giorno e
    tenuto per ``anni`` anni, quanto avresti reso **in media all'anno** (CAGR).

    Restituisce una Series indicizzata per data di partenza. Le date troppo
    recenti (per cui la finestra di ``anni`` anni non rientra nello storico
    disponibile) vengono escluse. Serve abbastanza storico: con finestre lunghe
    i punti disponibili sono pochi.
    """
    r = serie_rendimenti.dropna()
    if r.empty:
        return pd.Series(dtype="float64")

    # Indice della ricchezza (1 € investito che cresce).
    ricchezza = (1.0 + r).cumprod()
    date = ricchezza.index
    valori = ricchezza.values
    n = len(date)
    if n == 0:
        return pd.Series(dtype="float64")

    # Per ogni partenza, la data obiettivo è t + "anni" (calendario).
    obiettivi = date + pd.DateOffset(years=anni)
    # Posizione dell'ultima data disponibile <= obiettivo.
    pos = date.searchsorted(obiettivi, side="right") - 1
    ultima = date[-1]

    indici, rendimenti_ann = [], []
    for i in range(n):
        if obiettivi[i] > ultima:
            continue  # finestra non completa nello storico
        j = int(pos[i])
        if j <= i:
            continue
        anni_eff = (date[j] - date[i]).days / 365.25
        if anni_eff <= 0:
            continue
        rapporto = valori[j] / valori[i]
        ann = -1.0 if rapporto <= 0 else rapporto ** (1.0 / anni_eff) - 1.0
        indici.append(date[i])
        rendimenti_ann.append(ann)

    return pd.Series(rendimenti_ann, index=pd.DatetimeIndex(indici))


# ---------------------------------------------------------------------------
# Pianificazione: PAC/DCA, proiezione a obiettivo, riepilogo automatico
# ---------------------------------------------------------------------------

def simula_pac(serie_rendimenti: pd.Series, importo: float = 100.0, frequenza_mesi: int = 1) -> dict | None:
    """Backtest storico di un PAC (versamenti periodici) vs investimento unico.

    Simula, sui dati reali del portafoglio, di versare ``importo`` ogni
    ``frequenza_mesi`` mesi (acquistando "quote" al prezzo di quel giorno) e lo
    confronta con un investimento unico iniziale dello stesso capitale totale.
    Restituisce un dizionario con i totali e le serie temporali per il grafico.
    """
    r = serie_rendimenti.dropna()
    if len(r) < 2:
        return None
    W = (1.0 + r).cumprod()              # indice di ricchezza (1 unità che cresce)
    idx = W.index

    # Prima seduta di ciascun mese, poi una ogni "frequenza_mesi" mesi.
    periodi = idx.to_period("M")
    primi = pd.Series(idx, index=periodi)
    primi = primi[~primi.index.duplicated(keep="first")]
    date_vers = pd.DatetimeIndex(primi.values[:: max(1, int(frequenza_mesi))])

    contrib = pd.Series(0.0, index=idx)
    contrib.loc[date_vers] = float(importo)
    quote_cum = (contrib / W).cumsum()   # quote accumulate giorno per giorno
    valore_pac = quote_cum * W
    versato = contrib.cumsum()
    tot_versato = float(versato.iloc[-1])

    # Investimento unico (lump sum): tutto il capitale finale versato, all'inizio.
    valore_lump = tot_versato * (W / W.iloc[0])

    serie = pd.DataFrame({
        "PAC": valore_pac,
        "Capitale versato": versato,
        "Investimento unico": valore_lump,
    })
    return {
        "n_versamenti": int((contrib > 0).sum()),
        "versato": tot_versato,
        "valore_finale": float(valore_pac.iloc[-1]),
        "guadagno_pct": float(valore_pac.iloc[-1] / tot_versato - 1.0) if tot_versato else np.nan,
        "lump_finale": float(valore_lump.iloc[-1]),
        "lump_guadagno_pct": float(valore_lump.iloc[-1] / tot_versato - 1.0) if tot_versato else np.nan,
        "serie": serie,
    }


def proiezione_obiettivo(
    mu_annuo: float, sigma_annuo: float, obiettivo: float, anni: int,
    prob_target: float = 0.75, n_sim: int = 2000, seed: int = 0,
) -> dict | None:
    """Proiezione FUTURA: versamento mensile per un obiettivo, a probabilità scelta.

    Con una **simulazione Monte Carlo** (rendimenti mensili ~Normale) calcola il
    versamento mensile necessario perché il portafoglio raggiunga ``obiettivo``
    euro tra ``anni`` anni **con probabilità ≈ ``prob_target``** (es. 75%), non
    solo "in media". Sfrutta la linearità: il valore finale è proporzionale al
    versamento, quindi PMT = obiettivo / (percentile (1−q) del valore accumulato
    da 1 €/mese). Restituisce PMT, probabilità effettiva, scenari e bande nel tempo.
    """
    n = int(anni * 12)
    if n <= 0:
        return None
    r_m = (1.0 + mu_annuo) ** (1.0 / 12.0) - 1.0
    sig_m = sigma_annuo / np.sqrt(12.0)
    rng = np.random.default_rng(seed)
    rendimenti = rng.normal(r_m, sig_m, size=(n_sim, n))

    # Valore accumulato versando 1 €/mese (per ogni simulazione e nel tempo).
    storia = np.empty((n_sim, n))
    g = np.zeros(n_sim)
    for t in range(n):
        g = (g + 1.0) * (1.0 + rendimenti[:, t])
        storia[:, t] = g
    g_finale = storia[:, -1]

    q = min(max(float(prob_target), 0.50), 0.95)
    soglia = float(np.percentile(g_finale, (1.0 - q) * 100.0))
    pmt = obiettivo / soglia if soglia > 0 else np.nan
    finale = pmt * g_finale

    bande_arr = np.percentile(storia, [10, 50, 90], axis=0) * pmt
    bande = pd.DataFrame(
        {"Pessimista (10%)": bande_arr[0], "Medio (50%)": bande_arr[1], "Ottimista (90%)": bande_arr[2],
         "Capitale versato": pmt * np.arange(1, n + 1)},
        index=np.arange(1, n + 1),
    )
    return {
        "pmt_mensile": float(pmt),
        "prob_target": q,
        "prob_effettiva": float((finale >= obiettivo).mean()),
        "totale_versato": float(pmt * n),
        "pessimista": float(np.percentile(finale, 10)),
        "medio": float(np.percentile(finale, 50)),
        "ottimista": float(np.percentile(finale, 90)),
        "bande": bande,
    }


def riepilogo_portafoglio(rendimenti: pd.DataFrame, pesi: pd.Series, orizzonte: int, risk_free: float = 0.0) -> dict:
    """Riepilogo automatico (testo in italiano semplice) del portafoglio.

    Classifica **diversificazione** (n. asset + correlazione media + concentrazione
    del contributo al rischio), **rischio** (volatilità annua) e **coerenza con
    l'orizzonte**. È una descrizione didattica, NON una raccomandazione.
    """
    colonne = list(rendimenti.columns)
    n_asset = len(colonne)
    met = metriche_portafoglio(rendimenti, pesi, risk_free)
    vol = met["Volatilità annua (covarianza)"]

    if np.isnan(vol):
        rischio = "indeterminato"
    elif vol < 0.08:
        rischio = "basso"
    elif vol < 0.15:
        rischio = "medio"
    else:
        rischio = "alto"

    corr = matrice_correlazione(rendimenti)
    if n_asset >= 2:
        m = corr.values
        iu = np.triu_indices_from(m, k=1)
        corr_media = float(np.nanmean(m[iu]))
    else:
        corr_media = np.nan
    rc = contributo_rischio(rendimenti, pesi)["Contributo %"]
    conc = float(rc.max()) if len(rc) else 1.0

    if n_asset <= 1:
        diversificazione = "nulla (un solo asset)"
    elif n_asset >= 4 and (np.isnan(corr_media) or corr_media < 0.6) and conc < 0.6:
        diversificazione = "buona"
    elif n_asset >= 2 and conc < 0.8:
        diversificazione = "media"
    else:
        diversificazione = "scarsa"

    if rischio == "alto" and orizzonte < 5:
        coerenza = (f"il rischio è **alto** rispetto a un orizzonte di {orizzonte} anni: "
                    "su orizzonti brevi le oscillazioni pesano di più")
    elif rischio == "basso" and orizzonte >= 10:
        coerenza = (f"profilo **prudente** per un orizzonte lungo ({orizzonte} anni): "
                    "meno oscillazioni, ma anche rendimenti attesi più contenuti")
    else:
        coerenza = f"rischio nel complesso **coerente** con un orizzonte di {orizzonte} anni"

    buono = (rischio != "alto" or orizzonte >= 7) and diversificazione in ("buona", "media")
    livello = "success" if buono else "warning"
    testo = (
        f"Portafoglio con **{n_asset} asset**, diversificazione **{diversificazione}** e "
        f"rischio **{rischio}** (volatilità annua {vol:.1%}). In sintesi: {coerenza}."
    )
    return {
        "testo": testo, "livello": livello, "rischio": rischio,
        "diversificazione": diversificazione, "vol": vol,
        "corr_media": corr_media, "concentrazione": conc,
    }


# ---------------------------------------------------------------------------
# Costi (TER) e fiscalità (stime didattiche)
# ---------------------------------------------------------------------------

def proiezione_costi(
    importo: float, rendimento_lordo: float, ter_pesato: float,
    aliquota_pesata: float, anni: int, bollo: float = 0.002,
) -> dict:
    """Stima l'impatto di costi (TER), bollo e tasse su un capitale nel tempo.

    Modello didattico: il rendimento annuo lordo viene ridotto dal **TER** e dal
    **bollo** (0,2%/anno) in modo composto; alla fine si applicano le **tasse**
    (aliquota sul guadagno, alla vendita). Restituisce i valori intermedi.
    """
    g = rendimento_lordo
    anni = max(0, int(anni))
    val_lordo = importo * (1.0 + g) ** anni
    val_dopo_ter = importo * (1.0 + g - ter_pesato) ** anni
    val_dopo_bollo = importo * (1.0 + g - ter_pesato - bollo) ** anni
    guadagno = max(val_dopo_bollo - importo, 0.0)
    tasse = guadagno * aliquota_pesata
    val_netto = val_dopo_bollo - tasse
    return {
        "val_lordo": float(val_lordo),
        "val_dopo_ter": float(val_dopo_ter),
        "costo_ter": float(val_lordo - val_dopo_ter),
        "val_dopo_bollo": float(val_dopo_bollo),
        "tasse": float(tasse),
        "val_netto": float(val_netto),
    }


# ---------------------------------------------------------------------------
# Ribilanciamento vs buy & hold
# ---------------------------------------------------------------------------

def simula_ribilanciamento(
    prezzi: pd.DataFrame, pesi: pd.Series, modo: str = "annuale", parametro: float = 0.05,
) -> dict:
    """Confronta **buy & hold** e **ribilanciamento** (annuale o a soglia).

    - buy & hold: quote iniziali fisse, i pesi derivano col tempo;
    - annuale: riporta ai pesi target ogni ~365 giorni;
    - a soglia: ribilancia quando un peso si scosta oltre ``parametro`` dal target.

    Restituisce le due curve (base 100), il numero di ribilanci e le serie dei
    rendimenti per le statistiche.
    """
    prezzi = prezzi.dropna()
    colonne = list(prezzi.columns)
    if prezzi.empty or len(colonne) < 1:
        return {"serie": pd.DataFrame(), "n_ribilanci": 0}
    w_target = normalizza_pesi(pesi, colonne).values
    P = prezzi.values.astype(float)
    n_giorni = P.shape[0]
    date = prezzi.index

    quote_bh = w_target / P[0]
    valore_bh = (quote_bh * P).sum(axis=1)

    valore_rb = np.empty(n_giorni)
    quote = w_target / P[0]
    n_rib = 0
    ultimo = date[0]
    for i in range(n_giorni):
        val = float((quote * P[i]).sum())
        valore_rb[i] = val
        pesi_correnti = quote * P[i] / val
        if modo == "annuale":
            ribilancia = (date[i] - ultimo).days >= 365
        else:  # a soglia
            ribilancia = float(np.max(np.abs(pesi_correnti - w_target))) > parametro
        if ribilancia and i < n_giorni - 1:
            quote = w_target * val / P[i]
            n_rib += 1
            ultimo = date[i]

    serie = pd.DataFrame(
        {"Buy & hold": 100.0 * valore_bh / valore_bh[0],
         "Ribilanciato": 100.0 * valore_rb / valore_rb[0]},
        index=date,
    )
    return {"serie": serie, "n_ribilanci": n_rib}


# ---------------------------------------------------------------------------
# Allocazione paese / settore
# ---------------------------------------------------------------------------

def aggrega_composizione(
    pesi: pd.Series,
    composizione: dict[str, dict[str, dict[str, float]]],
    tipo: str,
) -> tuple[pd.Series, list[str]]:
    """Aggrega la composizione (``paese`` o ``settore``) a livello portafoglio.

    Per ogni asset con composizione disponibile, i pesi delle categorie
    vengono moltiplicati per il peso dell'asset nel portafoglio e sommati.
    I pesi di ciascun asset vengono normalizzati a 1 prima dell'aggregazione
    (così asset con composizione parziale non vengono sottopesati).

    Restituisce:
    - una Series categoria -> peso aggregato (normalizzato sugli asset coperti);
    - la lista dei ticker **senza** composizione disponibile (da segnalare).
    """
    pesi = normalizza_pesi(pesi, list(pesi.index))
    aggregato: dict[str, float] = {}
    mancanti: list[str] = []
    peso_coperto = 0.0

    for ticker, peso in pesi.items():
        comp_asset = composizione.get(ticker, {}).get(tipo, {})
        if not comp_asset:
            mancanti.append(ticker)
            continue
        tot = sum(comp_asset.values())
        if tot <= 0:
            mancanti.append(ticker)
            continue
        peso_coperto += peso
        for categoria, q in comp_asset.items():
            # normalizza la composizione del singolo asset a somma 1
            aggregato[categoria] = aggregato.get(categoria, 0.0) + peso * (q / tot)

    serie = pd.Series(aggregato, dtype="float64").sort_values(ascending=False)
    # Riporta a somma 1 rispetto al solo peso effettivamente coperto.
    if peso_coperto > 0:
        serie = serie / peso_coperto
    return serie, mancanti


def coppie_sovrapposte(distribuzioni: dict[str, dict[str, float]], soglia: float = 0.9):
    """Coppie di asset con distribuzioni molto **simili** (cosine ≥ soglia).

    ``distribuzioni`` = {ticker: {categoria: frazione}} (es. ripartizione per
    paese). Serve a segnalare asset che espongono in gran parte agli stessi
    mercati/aziende (es. MSCI World e S&P 500). Restituisce
    ``[(ticker_a, ticker_b, similarità), ...]``.
    """
    items = [(t, d) for t, d in distribuzioni.items() if d]
    coppie = []
    for i in range(len(items)):
        ta, da = items[i]
        for j in range(i + 1, len(items)):
            tb, db = items[j]
            chiavi = set(da) | set(db)
            va = np.array([da.get(k, 0.0) for k in chiavi])
            vb = np.array([db.get(k, 0.0) for k in chiavi])
            na, nb = np.linalg.norm(va), np.linalg.norm(vb)
            if na == 0 or nb == 0:
                continue
            sim = float(va @ vb / (na * nb))
            if sim >= soglia:
                coppie.append((ta, tb, sim))
    return coppie


# ---------------------------------------------------------------------------
# Extra: minima varianza e frontiera efficiente
# ---------------------------------------------------------------------------

def _peso_minimo(frazione_minima: float, n: int, long_only: bool) -> float:
    """Soglia inferiore L (peso minimo per asset) dalla frazione α.

    La regola è L = α · (1/N): ogni asset pesa almeno una frazione α della
    quota equipesata. Così il vincolo è SEMPRE ammissibile (N·L = α ≤ 1) per
    qualunque numero di asset, a differenza di una soglia fissa. Il vincolo ha
    senso solo in modalità long-only; con gli short ammessi si ignora (L = 0).
    """
    if not long_only or frazione_minima <= 0 or n <= 0:
        return 0.0
    # α viene limitato a [0, 1]; L non può superare la quota equa 1/N.
    alpha = min(max(float(frazione_minima), 0.0), 1.0)
    return alpha / n


def _limiti_peso(frazione_minima: float, n: int, long_only: bool, peso_max: float = 1.0):
    """Restituisce ``(lower, upper)`` per i pesi nell'ottimizzazione.

    In long-only: lower = L = α·(1/N) (quota minima); upper = ``peso_max`` (cap
    massimo per asset) clampato a ≥ 1/N — così la somma può comunque arrivare a 1
    — e con L ≤ upper. Con gli short ammessi: ``(-1, 1)``.
    """
    if not long_only:
        return -1.0, 1.0
    L = _peso_minimo(frazione_minima, n, long_only)
    pm = min(1.0, max(float(peso_max), 1.0 / n))
    return min(L, pm), pm


def pesi_minima_varianza(
    rendimenti: pd.DataFrame, long_only: bool = True, frazione_minima: float = 0.0,
    peso_max: float = 1.0,
) -> pd.Series:
    """Pesi del portafoglio a minima varianza globale.

    Con ``long_only=True`` e scipy disponibile si impone L ≤ w ≤ ``peso_max`` e
    Σw = 1 tramite ottimizzazione (L = quota minima, ``peso_max`` = cap per asset).
    Senza scipy (o con short ammessi) si usa la soluzione analitica non vincolata.
    """
    colonne = list(rendimenti.columns)
    n = len(colonne)
    sigma = matrice_covarianza_annua(rendimenti).values
    lo, hi = _limiti_peso(frazione_minima, n, long_only, peso_max)

    # Caso limite: soglia = quota equa -> unico portafoglio ammissibile (equipeso).
    if long_only and n * lo >= 1.0 - 1e-9:
        return pd.Series(1.0 / n, index=colonne)

    if long_only and SCIPY_DISPONIBILE:
        def varianza(w):
            return float(w @ sigma @ w)

        vincoli = [{"type": "eq", "fun": lambda w: np.sum(w) - 1.0}]
        limiti = [(lo, hi)] * n
        w0 = np.full(n, 1.0 / n)
        res = minimize(varianza, w0, method="SLSQP", bounds=limiti, constraints=vincoli)
        w = res.x if res.success else w0
    else:
        uno = np.ones(n)
        try:
            inv = np.linalg.pinv(sigma)
            w = inv @ uno / (uno @ inv @ uno)
        except np.linalg.LinAlgError:
            w = np.full(n, 1.0 / n)

    return pd.Series(w, index=colonne)


def frontiera_efficiente(
    rendimenti: pd.DataFrame,
    n_punti: int = 40,
    long_only: bool = True,
    frazione_minima: float = 0.0,
    peso_max: float = 1.0,
) -> pd.DataFrame:
    """Calcola la frontiera efficiente (richiede scipy).

    Restituisce un DataFrame con colonne ``vol`` e ``rend`` per ``n_punti``
    livelli di rendimento target tra il minimo e il massimo rendimento medio
    annuo degli asset. La quota minima per asset (``frazione_minima``) viene
    applicata anche qui, così i portafogli ottimali calcolati con la stessa
    soglia giacciono sulla frontiera disegnata. Se scipy non è disponibile
    ritorna un DataFrame vuoto.
    """
    if not SCIPY_DISPONIBILE:
        return pd.DataFrame(columns=["vol", "rend"])

    colonne = list(rendimenti.columns)
    n = len(colonne)
    sigma = matrice_covarianza_annua(rendimenti).values
    mu = rendimenti.mean().values * GIORNI_BORSA  # rendimento medio annuo per asset
    lo, hi = _limiti_peso(frazione_minima, n, long_only, peso_max)

    target_min, target_max = mu.min(), mu.max()
    obiettivi = np.linspace(target_min, target_max, n_punti)

    limiti = [(lo, hi)] * n
    w0 = np.full(n, 1.0 / n)

    punti = []
    for target in obiettivi:
        vincoli = [
            {"type": "eq", "fun": lambda w: np.sum(w) - 1.0},
            {"type": "eq", "fun": lambda w, t=target: float(w @ mu) - t},
        ]
        res = minimize(
            lambda w: float(w @ sigma @ w),
            w0,
            method="SLSQP",
            bounds=limiti,
            constraints=vincoli,
        )
        if res.success:
            vol = float(np.sqrt(max(res.x @ sigma @ res.x, 0.0)))
            punti.append({"vol": vol, "rend": float(target)})

    return pd.DataFrame(punti)


def pesi_massimo_rendimento(
    rendimenti: pd.DataFrame, long_only: bool = True, frazione_minima: float = 0.0,
    peso_max: float = 1.0,
) -> pd.Series:
    """Pesi che massimizzano il rendimento medio annuo atteso.

    Obiettivo lineare con vincoli L ≤ w ≤ ``peso_max`` e Σw = 1: si mette la quota
    minima L su ogni asset e si distribuisce il resto, in modo **greedy**, sugli
    asset col rendimento atteso più alto fino al cap ``peso_max``. Così, con un
    cap < 100%, il rendimento non si concentra tutto su un solo asset.
    """
    colonne = list(rendimenti.columns)
    n = len(colonne)
    mu = rendimenti.mean().values * GIORNI_BORSA  # rendimento medio annuo per asset
    lo, hi = _limiti_peso(frazione_minima, n, long_only, peso_max)

    if not long_only:
        w = np.zeros(n)
        w[int(np.argmax(mu))] = 1.0
        return pd.Series(w, index=colonne)
    if n * lo >= 1.0 - 1e-9:
        return pd.Series(1.0 / n, index=colonne)

    w = np.full(n, lo)
    rimanente = 1.0 - n * lo
    for idx in np.argsort(mu)[::-1]:  # dagli asset col rendimento più alto
        aggiunta = min(hi - lo, rimanente)
        w[int(idx)] += aggiunta
        rimanente -= aggiunta
        if rimanente <= 1e-12:
            break
    return pd.Series(w, index=colonne)


def pesi_massimo_sharpe(
    rendimenti: pd.DataFrame,
    risk_free: float = 0.0,
    long_only: bool = True,
    frazione_minima: float = 0.0,
    peso_max: float = 1.0,
) -> pd.Series:
    """Pesi che massimizzano l'indice di Sharpe (portafoglio di tangenza).

    Massimizza (wᵀμ − rf) / √(wᵀ Σ w) con Σ e μ annualizzati, Σw = 1 e vincoli
    L ≤ w ≤ ``peso_max`` (in long-only). Usa scipy se disponibile; altrimenti la
    soluzione analitica di tangenza w ∝ Σ⁻¹ (μ − rf) (può dare pesi negativi).
    """
    colonne = list(rendimenti.columns)
    n = len(colonne)
    sigma = matrice_covarianza_annua(rendimenti).values
    mu = rendimenti.mean().values * GIORNI_BORSA
    lo, hi = _limiti_peso(frazione_minima, n, long_only, peso_max)

    if long_only and n * lo >= 1.0 - 1e-9:
        return pd.Series(1.0 / n, index=colonne)

    if not SCIPY_DISPONIBILE:
        inv = np.linalg.pinv(sigma)
        w = inv @ (mu - risk_free)
        somma = w.sum()
        if somma != 0:
            w = w / somma
        return pd.Series(w, index=colonne)

    def neg_sharpe(w):
        ret = float(w @ mu)
        vol = float(np.sqrt(max(w @ sigma @ w, 1e-12)))
        return -(ret - risk_free) / vol

    vincoli = [{"type": "eq", "fun": lambda w: np.sum(w) - 1.0}]
    limiti = [(lo, hi)] * n
    w0 = np.full(n, 1.0 / n)
    res = minimize(neg_sharpe, w0, method="SLSQP", bounds=limiti, constraints=vincoli)
    w = res.x if res.success else w0
    return pd.Series(w, index=colonne)


def pesi_risk_parity(rendimenti: pd.DataFrame, peso_max: float = 1.0) -> pd.Series:
    """Pesi a **parità di rischio** (Equal Risk Contribution, ERC).

    Cerca pesi (long-only, Σw = 1) per cui **ogni asset contribuisce alla stessa
    misura** alla volatilità del portafoglio. Risultato: gli asset più volatili
    pesano meno, quelli più tranquilli di più. Con scipy minimizza la varianza dei
    contributi al rischio; senza scipy usa il proxy "inverse volatility".
    """
    colonne = list(rendimenti.columns)
    n = len(colonne)
    if n < 2:
        return pd.Series(1.0 / max(n, 1), index=colonne)
    sigma = matrice_covarianza_annua(rendimenti).values

    if not SCIPY_DISPONIBILE:
        vol = np.sqrt(np.diag(sigma))
        w = (1.0 / vol)
        return pd.Series(w / w.sum(), index=colonne)

    def obiettivo(w):
        var = float(w @ sigma @ w)
        if var <= 1e-12:
            return 0.0
        # Contributi al rischio in frazione (sommano a 1); target = 1/n per ciascuno.
        pct = (w * (sigma @ w)) / var
        return float(np.sum((pct - 1.0 / n) ** 2))

    hi = min(1.0, max(float(peso_max), 1.0 / n))
    vincoli = [{"type": "eq", "fun": lambda w: np.sum(w) - 1.0}]
    limiti = [(1e-6, hi)] * n
    w0 = np.full(n, 1.0 / n)
    res = minimize(obiettivo, w0, method="SLSQP", bounds=limiti, constraints=vincoli,
                   options={"maxiter": 500, "ftol": 1e-12})
    w = res.x if res.success else w0
    w = np.clip(w, 0.0, None)
    return pd.Series(w / w.sum(), index=colonne)


def pesi_ottimizzati(
    rendimenti: pd.DataFrame,
    obiettivo: str,
    risk_free: float = 0.0,
    long_only: bool = True,
    frazione_minima: float = 0.0,
    peso_max: float = 1.0,
) -> pd.Series:
    """Dispatcher: restituisce i pesi ottimali per l'obiettivo scelto.

    ``obiettivo`` ∈ {"min_var", "max_ret", "max_sharpe", "risk_parity"}.
    ``frazione_minima`` = quota minima per asset (α in L = α·(1/N)); ``peso_max`` =
    cap massimo per asset (frazione).
    """
    if obiettivo == "min_var":
        return pesi_minima_varianza(rendimenti, long_only, frazione_minima, peso_max)
    if obiettivo == "max_ret":
        return pesi_massimo_rendimento(rendimenti, long_only, frazione_minima, peso_max)
    if obiettivo == "max_sharpe":
        return pesi_massimo_sharpe(rendimenti, risk_free, long_only, frazione_minima, peso_max)
    if obiettivo == "risk_parity":
        return pesi_risk_parity(rendimenti, peso_max)
    raise ValueError(f"Obiettivo non riconosciuto: {obiettivo}")


# ---------------------------------------------------------------------------
# Indicatori di analisi tecnica
# ---------------------------------------------------------------------------

def media_mobile(prezzi: pd.Series, finestra: int) -> pd.Series:
    """Media mobile semplice (SMA) sui prezzi, su ``finestra`` giorni."""
    return prezzi.rolling(int(finestra), min_periods=1).mean()


def media_mobile_esp(prezzi: pd.Series, finestra: int) -> pd.Series:
    """Media mobile esponenziale (EMA) sui prezzi, con span ``finestra``."""
    return prezzi.ewm(span=int(finestra), adjust=False).mean()


def rsi(prezzi: pd.Series, periodo: int = 14) -> pd.Series:
    """Relative Strength Index (RSI) con smoothing di Wilder.

    Valori 0–100: convenzionalmente >70 = ipercomprato, <30 = ipervenduto.
    """
    delta = prezzi.diff()
    guadagno = delta.clip(lower=0.0)
    perdita = -delta.clip(upper=0.0)
    # Media esponenziale alla Wilder (alpha = 1/periodo).
    media_g = guadagno.ewm(alpha=1.0 / periodo, adjust=False, min_periods=periodo).mean()
    media_p = perdita.ewm(alpha=1.0 / periodo, adjust=False, min_periods=periodo).mean()
    rs = media_g / media_p.replace(0.0, np.nan)
    return 100.0 - 100.0 / (1.0 + rs)


# ---------------------------------------------------------------------------
# Indicatori statistici: valutazione, RSI, vantaggio, semaforo del rischio
# ---------------------------------------------------------------------------
# NB: sono indicatori statistici/storici a scopo didattico, NON consigli di
# acquisto/vendita. I rendimenti passati non predicono quelli futuri.

def valutazione_prezzo(prezzo: pd.Series, finestra: int = 200) -> dict:
    """Dice se il livello attuale è "caro" o "economico" rispetto alla SUA media.

    Confronto statistico-tecnico (non fondamentale): prezzo corrente vs media
    mobile su ``finestra`` giorni. Restituisce premio/sconto % e z-score
    (di quante deviazioni standard il prezzo è sopra/sotto la media).
    """
    p = prezzo.dropna()
    vuoto = {"prezzo": np.nan, "riferimento": np.nan, "premio": np.nan,
             "z": np.nan, "giudizio": "Dati insufficienti", "giudizio_breve": "—"}
    if len(p) < 20:
        return vuoto
    w = min(int(finestra), len(p))
    media = float(p.rolling(w).mean().iloc[-1])
    sd = float(p.rolling(w).std().iloc[-1])
    prezzo_corr = float(p.iloc[-1])
    premio = prezzo_corr / media - 1.0 if media else np.nan
    z = (prezzo_corr - media) / sd if sd and sd > 0 else np.nan

    # Etichette NEUTRE (descrivono la posizione vs media, senza suggerire azioni).
    if np.isnan(z):
        g, gb = "Indeterminato", "—"
    elif z > 2:
        g, gb = "Molto sopra la media storica", "Molto sopra la media"
    elif z > 1:
        g, gb = "Sopra la media storica", "Sopra la media"
    elif z < -2:
        g, gb = "Molto sotto la media storica", "Molto sotto la media"
    elif z < -1:
        g, gb = "Sotto la media storica", "Sotto la media"
    else:
        g, gb = "In linea con la media storica", "In linea"

    return {"prezzo": prezzo_corr, "riferimento": media, "premio": premio,
            "z": z, "giudizio": g, "giudizio_breve": gb}


def giudizio_rsi(valore: float) -> str:
    """Etichetta dell'RSI: ipercomprato / ipervenduto / neutro."""
    if valore is None or np.isnan(valore):
        return "—"
    if valore >= 70:
        return "Ipercomprato"
    if valore <= 30:
        return "Ipervenduto"
    return "Neutro"


def vantaggio_statistico(rendimenti: pd.Series, risk_free: float = 0.0) -> dict:
    """Sintetizza il "vantaggio statistico" storico di una serie di rendimenti.

    Combina rendimento annualizzato (CAGR), indice di Sharpe e win-rate
    (quota di finestre di 1 anno chiuse in positivo). Restituisce un giudizio
    favorevole / neutro / sfavorevole basato sullo Sharpe storico.
    """
    r = rendimenti.dropna()
    if len(r) < 2:
        return {"cagr": np.nan, "sharpe": np.nan, "win_rate": np.nan, "giudizio": "—"}
    cagr_v = cagr(r)
    sharpe_v = sharpe(r, risk_free)
    roll1 = rolling_rendimenti_annualizzati(r, 1)
    win = float((roll1 > 0).mean()) if not roll1.empty else np.nan

    if np.isnan(sharpe_v):
        g = "—"
    elif sharpe_v >= 0.75:
        g = "Favorevole"
    elif sharpe_v <= 0:
        g = "Sfavorevole"
    else:
        g = "Neutro"
    return {"cagr": cagr_v, "sharpe": sharpe_v, "win_rate": win, "giudizio": g}


# Colori ed etichette delle 5 fasce del semaforo del rischio.
SEMAFORO_COLORI = {1: "#b3261e", 2: "#e8705f", 3: "#bdbdbd", 4: "#7fc97f", 5: "#2e7d32"}
SEMAFORO_ETICHETTE = {
    1: "Molto sfavorevole al rischio",
    2: "Sfavorevole al rischio",
    3: "Neutro",
    4: "Favorevole al rischio",
    5: "Molto favorevole al rischio",
}


def semaforo_rischio(prezzo: pd.Series) -> dict:
    """Semaforo statistico 1–5: quanto è "favorevole" il momento per il rischio.

    Punteggio composito (media di 3 segnali, ciascuno normalizzato in [-1, +1]):
    - **trend**: prezzo sopra/sotto la media mobile a 200 giorni;
    - **volatilità**: volatilità recente (21g) sotto/sopra la sua mediana storica
      (bassa = favorevole, alta = sfavorevole);
    - **momentum**: rendimento degli ultimi ~6 mesi (126 giorni).

    Mappa il composito su 1–5: 1–2 = sfavorevole (rosso), 3 = neutro (grigio),
    4–5 = favorevole (verde). ``valore`` è la versione continua (1.0–5.0) per il
    gauge; ``banda`` è l'intero 1–5.
    """
    p = prezzo.dropna()
    if len(p) < 30:
        return {"banda": 3, "valore": 3.0, "colore": SEMAFORO_COLORI[3],
                "etichetta": "Dati insufficienti", "trend": np.nan,
                "volatilita": np.nan, "momentum": np.nan}

    ret = p.pct_change()
    prezzo_corr = float(p.iloc[-1])

    # 1) Trend vs media 200 giorni: +10% sopra -> +1, -10% sotto -> -1.
    sma = float(p.rolling(min(200, len(p))).mean().iloc[-1])
    s_trend = float(np.clip((prezzo_corr / sma - 1.0) / 0.10, -1, 1)) if sma > 0 else 0.0

    # 2) Regime di volatilità: vol recente vs mediana storica (più bassa = meglio).
    vol = ret.rolling(min(21, len(ret))).std() * np.sqrt(GIORNI_BORSA)
    vol_corr = float(vol.iloc[-1])
    vol_med = float(vol.median())
    s_vol = float(np.clip(1.0 - vol_corr / vol_med, -1, 1)) if vol_med > 0 else 0.0

    # 3) Momentum a ~6 mesi: +15% -> +1, -15% -> -1.
    k = min(126, len(p) - 1)
    mom = prezzo_corr / float(p.iloc[-1 - k]) - 1.0 if k > 0 else 0.0
    s_mom = float(np.clip(mom / 0.15, -1, 1))

    comp = float(np.nanmean([s_trend, s_vol, s_mom]))
    valore = float(np.clip(3.0 + comp * 2.0, 1.0, 5.0))  # versione continua 1–5

    if comp <= -0.6:
        banda = 1
    elif comp <= -0.2:
        banda = 2
    elif comp < 0.2:
        banda = 3
    elif comp < 0.6:
        banda = 4
    else:
        banda = 5

    return {"banda": banda, "valore": valore, "colore": SEMAFORO_COLORI[banda],
            "etichetta": SEMAFORO_ETICHETTE[banda], "trend": s_trend,
            "volatilita": s_vol, "momentum": s_mom}
