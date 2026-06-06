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


def pesi_minima_varianza(
    rendimenti: pd.DataFrame, long_only: bool = True, frazione_minima: float = 0.0
) -> pd.Series:
    """Pesi del portafoglio a minima varianza globale.

    Con ``long_only=True`` e scipy disponibile si impone L ≤ w ≤ 1 e Σw = 1
    tramite ottimizzazione, dove L = ``frazione_minima``·(1/N) è la quota
    minima per asset (vedi :func:`_peso_minimo`). Senza scipy (o con short
    ammessi) si usa la soluzione analitica non vincolata, che può dare pesi
    negativi e non rispetta la soglia minima.
    """
    colonne = list(rendimenti.columns)
    n = len(colonne)
    sigma = matrice_covarianza_annua(rendimenti).values
    L = _peso_minimo(frazione_minima, n, long_only)

    # Caso limite: soglia = quota equa -> unico portafoglio ammissibile (equipeso).
    if long_only and n * L >= 1.0 - 1e-9:
        return pd.Series(1.0 / n, index=colonne)

    if long_only and SCIPY_DISPONIBILE:
        def varianza(w):
            return float(w @ sigma @ w)

        vincoli = [{"type": "eq", "fun": lambda w: np.sum(w) - 1.0}]
        limiti = [(L, 1.0)] * n
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
    L = _peso_minimo(frazione_minima, n, long_only)

    target_min, target_max = mu.min(), mu.max()
    obiettivi = np.linspace(target_min, target_max, n_punti)

    limiti = [(L, 1.0)] * n if long_only else [(-1.0, 1.0)] * n
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
    rendimenti: pd.DataFrame, long_only: bool = True, frazione_minima: float = 0.0
) -> pd.Series:
    """Pesi che massimizzano il rendimento medio annuo atteso.

    Senza quota minima (``frazione_minima`` = 0) la soluzione long-only è
    degenere: tutto il capitale sull'asset col rendimento medio storico più
    alto. Con una quota minima L = α·(1/N) per asset, l'obiettivo lineare è
    massimizzato mettendo L su ogni asset e il resto (1 − N·L) sull'asset col
    rendimento atteso maggiore: così nessun asset è a zero.
    """
    colonne = list(rendimenti.columns)
    n = len(colonne)
    mu = rendimenti.mean().values * GIORNI_BORSA  # rendimento medio annuo per asset
    L = _peso_minimo(frazione_minima, n, long_only)

    if long_only and n * L >= 1.0 - 1e-9:
        return pd.Series(1.0 / n, index=colonne)

    w = np.full(n, L)
    w[int(np.argmax(mu))] += 1.0 - n * L  # il residuo va sull'asset migliore
    return pd.Series(w, index=colonne)


def pesi_massimo_sharpe(
    rendimenti: pd.DataFrame,
    risk_free: float = 0.0,
    long_only: bool = True,
    frazione_minima: float = 0.0,
) -> pd.Series:
    """Pesi che massimizzano l'indice di Sharpe (portafoglio di tangenza).

    Massimizza (wᵀμ − rf) / √(wᵀ Σ w) con Σ e μ annualizzati, somma pesi = 1 e
    quota minima L = α·(1/N) per asset (in long-only). Usa scipy se disponibile;
    altrimenti ripiega sulla soluzione analitica di tangenza w ∝ Σ⁻¹ (μ − rf)
    (che può dare pesi negativi e non rispetta la soglia minima).
    """
    colonne = list(rendimenti.columns)
    n = len(colonne)
    sigma = matrice_covarianza_annua(rendimenti).values
    mu = rendimenti.mean().values * GIORNI_BORSA
    L = _peso_minimo(frazione_minima, n, long_only)

    if long_only and n * L >= 1.0 - 1e-9:
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
    limiti = [(L, 1.0)] * n if long_only else [(-1.0, 1.0)] * n
    w0 = np.full(n, 1.0 / n)
    res = minimize(neg_sharpe, w0, method="SLSQP", bounds=limiti, constraints=vincoli)
    w = res.x if res.success else w0
    return pd.Series(w, index=colonne)


def pesi_ottimizzati(
    rendimenti: pd.DataFrame,
    obiettivo: str,
    risk_free: float = 0.0,
    long_only: bool = True,
    frazione_minima: float = 0.0,
) -> pd.Series:
    """Dispatcher: restituisce i pesi ottimali per l'obiettivo scelto.

    ``obiettivo`` ∈ {"min_var", "max_ret", "max_sharpe"}.
    ``frazione_minima`` è la quota minima per asset come frazione della quota
    equipesata (α in L = α·(1/N)); 0 = nessun vincolo.
    """
    if obiettivo == "min_var":
        return pesi_minima_varianza(rendimenti, long_only=long_only, frazione_minima=frazione_minima)
    if obiettivo == "max_ret":
        return pesi_massimo_rendimento(rendimenti, long_only=long_only, frazione_minima=frazione_minima)
    if obiettivo == "max_sharpe":
        return pesi_massimo_sharpe(
            rendimenti, risk_free=risk_free, long_only=long_only, frazione_minima=frazione_minima
        )
    raise ValueError(f"Obiettivo non riconosciuto: {obiettivo}")


# ---------------------------------------------------------------------------
# Indicatori di analisi tecnica
# ---------------------------------------------------------------------------

def media_mobile(prezzi: pd.Series, finestra: int) -> pd.Series:
    """Media mobile semplice (SMA) sui prezzi, su ``finestra`` giorni."""
    return prezzi.rolling(int(finestra), min_periods=1).mean()


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
