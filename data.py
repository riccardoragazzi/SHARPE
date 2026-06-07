"""
data.py
=======
Download e pulizia dei dati di mercato per ETF / indici.

Responsabilità del modulo:
- scaricare lo storico prezzi da yfinance (gestendo i suffissi di borsa);
- allineare le serie sull'intervallo di date comune a tutti gli asset e
  gestire i valori mancanti;
- convertire (opzionalmente) tutti i prezzi nella valuta base usando i
  tassi di cambio scaricabili da yfinance (es. ``EURUSD=X``);
- recuperare, dove disponibile, la composizione settoriale tramite
  ``Ticker.funds_data.sector_weightings``;
- caricare/salvare la composizione (paese/settore) inserita a mano da CSV.

Tutti i calcoli numerici veri e propri sono in ``metrics.py``: qui ci si
occupa solo di ottenere dei prezzi "puliti".
"""

from __future__ import annotations

import io
import re
from dataclasses import dataclass, field

import numpy as np
import pandas as pd
import yfinance as yf


def _e_isin(testo: str) -> bool:
    """True se la stringa ha la forma di un ISIN (es. IE00B4L5Y983)."""
    return bool(re.fullmatch(r"[A-Za-z]{2}[A-Za-z0-9]{9}[0-9]", (testo or "").strip()))

# Mappa indicativa suffisso di borsa -> descrizione, usata solo per aiutare
# l'utente nell'interfaccia. yfinance richiede il ticker già col suffisso
# corretto (es. "SWDA.MI" per Borsa Italiana).
SUFFISSI_BORSA = {
    ".MI": "Borsa Italiana (Milano)",
    ".DE": "Xetra (Germania)",
    ".AS": "Euronext Amsterdam",
    ".PA": "Euronext Parigi",
    ".L": "London Stock Exchange",
    ".SW": "SIX Swiss Exchange",
    ".MC": "Bolsa de Madrid",
    ".BR": "Euronext Bruxelles",
    ".VI": "Wiener Börse (Vienna)",
    ".TO": "Toronto Stock Exchange",
}


@dataclass
class RisultatoDownload:
    """Contenitore del risultato di un download di prezzi.

    Attributi
    ---------
    prezzi:
        DataFrame dei prezzi (close aggiustati) allineati, una colonna per
        ticker scaricato con successo. Indice = date di borsa.
    valute:
        Mappa ticker -> valuta nativa di quotazione (es. "EUR", "USD").
    errori:
        Mappa ticker -> messaggio d'errore per i ticker non scaricabili.
    valuta_base:
        Valuta in cui sono espressi i prezzi nel DataFrame ``prezzi``.
        Coincide con le valute native se la conversione è disattivata.
    """

    prezzi: pd.DataFrame
    valute: dict[str, str] = field(default_factory=dict)
    errori: dict[str, str] = field(default_factory=dict)
    valuta_base: str | None = None


def normalizza_ticker(ticker: str) -> str:
    """Ripulisce un ticker inserito dall'utente (spazi, maiuscole)."""
    return ticker.strip().upper()


def _serie_close(tk: yf.Ticker, period: str | None, start, end) -> pd.Series:
    """Scarica la serie dei prezzi 'Close' aggiustati per un singolo ticker.

    Usa ``auto_adjust=True`` così il prezzo tiene conto di dividendi e split:
    è la scelta corretta per analizzare il rendimento *total return*.
    L'indice viene reso "naive" (senza fuso orario) per poter allineare
    senza problemi asset quotati su borse diverse.
    """
    if period:
        hist = tk.history(period=period, auto_adjust=True)
    else:
        hist = tk.history(start=start, end=end, auto_adjust=True)

    if hist is None or hist.empty or "Close" not in hist.columns:
        return pd.Series(dtype="float64")

    serie = hist["Close"].copy()
    # Rimuove il fuso orario dall'indice per un allineamento uniforme.
    if isinstance(serie.index, pd.DatetimeIndex) and serie.index.tz is not None:
        serie.index = serie.index.tz_localize(None)
    serie.index = serie.index.normalize()
    return serie


def _valuta_nativa(tk: yf.Ticker) -> str | None:
    """Ricava la valuta di quotazione del ticker (con doppio fallback).

    Restituisce il codice **grezzo** (senza forzare le maiuscole), perché le
    valute in sottounità — es. ``GBp`` (penny) — si distinguono solo dalla
    minuscola: la normalizzazione avviene in :func:`_normalizza_valuta`.
    """
    try:
        cur = tk.fast_info.get("currency")
        if cur:
            return str(cur)
    except Exception:
        pass
    try:
        cur = tk.info.get("currency")
        if cur:
            return str(cur)
    except Exception:
        pass
    return None


def _normalizza_valuta(cur: str | None) -> tuple[str | None, float]:
    """Mappa una valuta (anche in sottounità) a ``(valuta_maggiore, divisore)``.

    Alcune borse quotano in **sottounità** (centesimi): es. ``GBp``/``GBX`` =
    penny britannici (1/100 di GBP), ``ZAc`` = centesimi di rand, ``ILA`` =
    agorot (1/100 di ILS). In questi casi i prezzi vanno **divisi per 100** e
    ricondotti alla valuta maggiore (per costruire correttamente la coppia di
    cambio). Le valute normali restituiscono ``(CUR, 1.0)``.
    """
    if not cur:
        return None, 1.0
    c = str(cur).strip()
    if c in ("GBp", "GBX", "GBx"):
        return "GBP", 100.0
    if c in ("ZAc", "ZAX"):
        return "ZAR", 100.0
    if c in ("ILA", "ILa"):
        return "ILS", 100.0
    return c.upper(), 1.0


def scarica_prezzi(
    tickers: list[str],
    period: str | None = "5y",
    start=None,
    end=None,
) -> RisultatoDownload:
    """Scarica i prezzi (close aggiustati) per una lista di ticker.

    Ogni ticker viene scaricato singolarmente così un ticker non valido non
    fa fallire l'intero download: gli errori vengono raccolti e segnalati.

    Parametri
    ---------
    tickers:
        lista di ticker già comprensivi di suffisso di borsa.
    period:
        periodo "comodo" di yfinance (es. "1y", "5y", "max"). Se ``start``
        è valorizzato, ``period`` viene ignorato.
    start, end:
        estremi espliciti dell'intervallo (hanno precedenza su ``period``).
    """
    series: dict[str, pd.Series] = {}
    valute: dict[str, str] = {}
    errori: dict[str, str] = {}

    usa_periodo = start is None
    for raw in tickers:
        t = normalizza_ticker(raw)
        if not t:
            continue
        try:
            tk = yf.Ticker(t)
            serie = _serie_close(tk, period if usa_periodo else None, start, end)
            if serie.empty:
                errori[t] = "Nessun dato disponibile (ticker inesistente o intervallo vuoto)."
                continue
            cur_major, divisore = _normalizza_valuta(_valuta_nativa(tk))
            if divisore != 1.0:
                serie = serie / divisore  # da sottounità (es. penny) a valuta maggiore
            series[t] = serie
            if cur_major:
                valute[t] = cur_major
        except Exception as exc:  # rete, ticker malformato, ecc.
            errori[t] = f"Errore nel download: {exc}"

    if not series:
        return RisultatoDownload(prezzi=pd.DataFrame(), valute=valute, errori=errori)

    # Concatena le serie in un unico DataFrame e allinea le date.
    prezzi = pd.concat(series, axis=1)
    prezzi = allinea_prezzi(prezzi)

    return RisultatoDownload(prezzi=prezzi, valute=valute, errori=errori)


def controlla_qualita(prezzi: pd.DataFrame) -> list[tuple[str, str]]:
    """Controlli di qualità sui dati scaricati (storico, buchi, anomalie).

    Restituisce una lista di ``(livello, messaggio)`` con ``livello`` ∈
    {"warning", "info"}, da mostrare nell'interfaccia senza bloccare l'analisi.
    """
    avvisi: list[tuple[str, str]] = []
    if prezzi is None or prezzi.empty:
        return avvisi

    anni = (prezzi.index.max() - prezzi.index.min()).days / 365.25
    if anni < 1.0:
        avvisi.append(("warning",
            f"Storico molto breve (~{anni:.1f} anni): le metriche annualizzate sono poco affidabili."))

    # Buchi: intervalli > 7 giorni tra due quotazioni consecutive.
    giorni = prezzi.index.to_series().diff().dt.days
    n_buchi = int((giorni > 7).sum())
    if n_buchi > 0:
        avvisi.append(("info",
            f"{n_buchi} interruzione/i nei dati (oltre 7 giorni senza quotazioni): "
            "potrebbero esserci festività lunghe o dati mancanti."))

    # Anomalie: variazioni giornaliere estreme (possibili errori della fonte).
    rend = prezzi.pct_change()
    n_anomalie = int((rend.abs() > 0.40).to_numpy().sum())
    if n_anomalie > 0:
        avvisi.append(("warning",
            f"{n_anomalie} variazione/i giornaliera/e anomala/e (oltre ±40%): "
            "possibili errori nei dati di Yahoo Finance, controlla i risultati."))

    return avvisi


def allinea_prezzi(prezzi: pd.DataFrame) -> pd.DataFrame:
    """Allinea le serie sull'intervallo comune e gestisce i buchi.

    Strategia:
    1. ordina per data;
    2. restringe l'intervallo a quello *comune* a tutti gli asset
       (max delle prime date valide -> min delle ultime date valide);
    3. riempie in avanti i buchi interni (borse con festività diverse);
    4. elimina eventuali righe ancora incomplete.
    """
    if prezzi.empty:
        return prezzi

    prezzi = prezzi.sort_index()

    # Prima e ultima data valida per ciascuna colonna.
    prime = prezzi.apply(lambda c: c.first_valid_index())
    ultime = prezzi.apply(lambda c: c.last_valid_index())
    inizio_comune = prime.max()
    fine_comune = ultime.min()

    if pd.isna(inizio_comune) or pd.isna(fine_comune) or inizio_comune > fine_comune:
        # Nessuna sovrapposizione temporale tra gli asset.
        return pd.DataFrame()

    prezzi = prezzi.loc[inizio_comune:fine_comune]
    # Riempie i buchi interni dovuti a calendari di borsa diversi.
    prezzi = prezzi.ffill()
    # Scarta righe ancora incomplete (di norma solo l'inizio).
    prezzi = prezzi.dropna(how="any")
    return prezzi


# ---------------------------------------------------------------------------
# Conversione valutaria
# ---------------------------------------------------------------------------

def scarica_cambio(da: str, a: str, period: str | None, start, end) -> pd.Series:
    """Scarica la serie del tasso di cambio per convertire ``da`` -> ``a``.

    Convenzione yfinance: il ticker ``"EURUSD=X"`` vale ~1.08, cioè quanti
    USD servono per 1 EUR (unità di ``a`` per 1 unità di ``da``). Quindi per
    convertire un prezzo da ``da`` ad ``a`` basta *moltiplicare* per questo
    tasso. Se la coppia diretta non è disponibile si prova l'inversa e si
    prende il reciproco.
    """
    if da == a:
        return pd.Series(dtype="float64")

    def _scarica(pair: str) -> pd.Series:
        tk = yf.Ticker(pair)
        return _serie_close(tk, period, start, end)

    # Coppia diretta: {da}{a}=X
    serie = _scarica(f"{da}{a}=X")
    if not serie.empty:
        return serie

    # Fallback: coppia inversa, di cui prendiamo il reciproco.
    inv = _scarica(f"{a}{da}=X")
    if not inv.empty:
        return 1.0 / inv

    return pd.Series(dtype="float64")


def converti_in_base(
    risultato: RisultatoDownload,
    valuta_base: str,
    period: str | None,
    start,
    end,
) -> RisultatoDownload:
    """Converte tutti i prezzi nella valuta base prima del calcolo rendimenti.

    Ogni colonna viene moltiplicata per il tasso di cambio (allineato per
    data e riempito in avanti) dalla sua valuta nativa alla valuta base.
    I ticker la cui valuta nativa è ignota vengono lasciati invariati ma
    segnalati in ``errori``.
    """
    if risultato.prezzi.empty:
        risultato.valuta_base = valuta_base
        return risultato

    prezzi = risultato.prezzi.copy()
    errori = dict(risultato.errori)

    for ticker in list(prezzi.columns):
        nativa = risultato.valute.get(ticker)
        if nativa is None:
            errori[ticker] = (
                "Valuta nativa sconosciuta: prezzi NON convertiti, "
                "lasciati nella valuta originale."
            )
            continue
        if nativa == valuta_base:
            continue  # già nella valuta base

        cambio = scarica_cambio(nativa, valuta_base, period, start, end)
        if cambio.empty:
            errori[ticker] = (
                f"Cambio {nativa}->{valuta_base} non disponibile: "
                "prezzi lasciati nella valuta originale."
            )
            continue

        # Allinea il cambio alle date dei prezzi (riempimento in avanti).
        cambio = cambio.reindex(prezzi.index.union(cambio.index)).ffill()
        cambio = cambio.reindex(prezzi.index)
        prezzi[ticker] = prezzi[ticker] * cambio

    # Dopo la conversione potrebbero esserci nuovi buchi (cambio mancante a inizio).
    prezzi = prezzi.dropna(how="any")

    return RisultatoDownload(
        prezzi=prezzi,
        valute=risultato.valute,
        errori=errori,
        valuta_base=valuta_base,
    )


# ---------------------------------------------------------------------------
# Composizione: settori (auto) e paesi/settori (manuale)
# ---------------------------------------------------------------------------

def scarica_settori(ticker: str) -> dict[str, float]:
    """Tenta di recuperare i pesi di settore di un ETF tramite yfinance.

    Restituisce una mappa settore -> peso (in frazione, somma ~1). Per molti
    ETF UCITS europei il dato non è disponibile: in tal caso ritorna ``{}``.
    """
    try:
        tk = yf.Ticker(normalizza_ticker(ticker))
        fd = tk.funds_data
        sw = fd.sector_weightings  # dict {settore: peso}
        if not sw:
            return {}
        # Normalizza in un dizionario pulito di float.
        out = {str(k): float(v) for k, v in dict(sw).items() if v is not None}
        return out
    except Exception:
        return {}


def scarica_asset_classes(ticker: str) -> dict[str, float]:
    """Recupera la composizione per **classe di attività** di un ETF da yfinance.

    Da ``Ticker.funds_data.asset_classes`` (stock/bond/cash/…), restituisce una
    mappa {Azioni, Obbligazioni, Liquidità, Altro} -> peso (frazione). Per molti
    ETF è disponibile; in caso contrario ritorna ``{}``. L'oro/le materie prime
    di solito finiscono in "Altro" (vanno eventualmente corretti a mano).
    """
    try:
        tk = yf.Ticker(normalizza_ticker(ticker))
        ac = tk.funds_data.asset_classes
        if not ac:
            return {}
        d = {k: float(v or 0.0) for k, v in dict(ac).items()}
        out = {
            "Azioni": d.get("stockPosition", 0.0) + d.get("preferredPosition", 0.0),
            "Obbligazioni": d.get("bondPosition", 0.0) + d.get("convertiblePosition", 0.0),
            "Liquidità": d.get("cashPosition", 0.0),
            "Altro": d.get("otherPosition", 0.0),
        }
        return {k: v for k, v in out.items() if v > 0.0005}
    except Exception:
        return {}


def carica_composizione_csv(contenuto: str | bytes) -> dict[str, dict[str, dict[str, float]]]:
    """Carica una composizione (paese/settore) per ticker da un CSV.

    Formato CSV atteso (intestazione obbligatoria)::

        ticker,tipo,categoria,peso
        SWDA.MI,paese,Stati Uniti,0.70
        SWDA.MI,paese,Giappone,0.06
        SWDA.MI,settore,Tecnologia,0.24
        AGGH.MI,paese,Stati Uniti,0.40
        ...

    - ``tipo`` deve essere ``paese`` oppure ``settore``;
    - ``peso`` può essere espresso in frazione (0.70) o in percentuale (70):
      se per un (ticker, tipo) la somma supera 1.5 si assume siano percentuali
      e si divide per 100.

    Restituisce una struttura::

        { ticker: {"paese": {cat: peso}, "settore": {cat: peso}} }
    """
    if isinstance(contenuto, bytes):
        contenuto = contenuto.decode("utf-8-sig")

    df = pd.read_csv(io.StringIO(contenuto))
    df.columns = [c.strip().lower() for c in df.columns]
    richieste = {"ticker", "tipo", "categoria", "peso"}
    if not richieste.issubset(df.columns):
        raise ValueError(
            "Il CSV deve avere le colonne: ticker, tipo, categoria, peso. "
            f"Trovate: {list(df.columns)}"
        )

    comp: dict[str, dict[str, dict[str, float]]] = {}
    for _, riga in df.iterrows():
        ticker = normalizza_ticker(str(riga["ticker"]))
        tipo = str(riga["tipo"]).strip().lower()
        if tipo not in ("paese", "settore"):
            continue
        categoria = str(riga["categoria"]).strip()
        try:
            peso = float(riga["peso"])
        except (TypeError, ValueError):
            continue
        comp.setdefault(ticker, {"paese": {}, "settore": {}})
        comp[ticker][tipo][categoria] = peso

    # Normalizza percentuali -> frazioni se necessario.
    for ticker, sezioni in comp.items():
        for tipo, mappa in sezioni.items():
            tot = sum(mappa.values())
            if tot > 1.5:  # quasi certamente espressi in percentuale
                comp[ticker][tipo] = {k: v / 100.0 for k, v in mappa.items()}

    return comp


def composizione_in_csv(comp: dict[str, dict[str, dict[str, float]]]) -> str:
    """Serializza una struttura di composizione nel formato CSV documentato."""
    righe = ["ticker,tipo,categoria,peso"]
    for ticker, sezioni in comp.items():
        for tipo in ("paese", "settore"):
            for categoria, peso in sezioni.get(tipo, {}).items():
                righe.append(f"{ticker},{tipo},{categoria},{peso}")
    return "\n".join(righe)


# ---------------------------------------------------------------------------
# Ricerca strumenti e nomi "veri"
# ---------------------------------------------------------------------------

def cerca_strumenti(query: str, max_results: int = 12) -> list[dict]:
    """Cerca ETF / indici / titoli per nome o ticker su Yahoo Finance.

    Usa l'endpoint di ricerca di Yahoo (stessa fonte dei prezzi). Restituisce
    una lista di dizionari con: ``symbol`` (il ticker da usare per scaricare i
    dati), ``nome`` (nome esteso), ``tipo`` (ETF, INDEX, EQUITY, ...) e
    ``borsa`` (mercato di quotazione). In caso di errore ritorna ``[]``.
    """
    query = (query or "").strip()
    if not query:
        return []

    # Priorità per tipo: ETF e indici prima, futures/valute/opzioni in fondo,
    # così cercando es. "S&P 500" non compaiono in cima i futures.
    priorita = {"ETF": 0, "INDEX": 1, "MUTUALFUND": 2, "EQUITY": 3}

    # Yahoo per query "generiche" (es. "S&P 500") restituisce a volte solo
    # futures. Interroghiamo anche la variante con "ETF" e uniamo i risultati,
    # così si trovano comunque gli ETF/indici cercati per nome.
    sub_query = [query]
    # Per un ISIN si cerca così com'è (niente variante "… ETF", che farebbe rumore).
    if not _e_isin(query) and "etf" not in query.lower():
        sub_query.append(f"{query} ETF")

    trovati: dict[str, dict] = {}  # symbol -> record (dedup mantenendo il primo)
    for sq in sub_query:
        try:
            ricerca = yf.Search(sq, max_results=max(max_results, 15))
            quotes = ricerca.quotes
        except Exception:
            continue
        for q in quotes:
            simbolo = q.get("symbol")
            if not simbolo or simbolo in trovati:
                continue
            trovati[simbolo] = {
                "symbol": simbolo,
                "nome": q.get("shortname") or q.get("longname") or simbolo,
                "tipo": (q.get("quoteType") or q.get("typeDisp") or "").upper(),
                "borsa": q.get("exchDisp") or q.get("exchange") or "",
            }

    risultati = list(trovati.values())
    # Ordinamento stabile per priorità di tipo (mantiene l'ordine a parità).
    risultati.sort(key=lambda r: priorita.get(r["tipo"], 9))
    return risultati[:max_results]


def nome_strumento(ticker: str) -> str:
    """Ricava il nome "vero" di uno strumento dal suo ticker.

    Prova ``longName`` poi ``shortName``; se non disponibili ritorna il ticker
    stesso (così l'interfaccia ha sempre qualcosa da mostrare).
    """
    t = normalizza_ticker(ticker)
    try:
        info = yf.Ticker(t).get_info()
        nome = info.get("longName") or info.get("shortName")
        if nome:
            return str(nome)
    except Exception:
        pass
    return t


def nomi_strumenti(tickers: list[str]) -> dict[str, str]:
    """Comodità: mappa ticker -> nome per una lista di ticker."""
    return {normalizza_ticker(t): nome_strumento(t) for t in tickers}


def isin_strumento(ticker: str) -> str:
    """Tenta di ricavare l'ISIN di un ticker da yfinance (spesso non disponibile).

    Restituisce l'ISIN se valido, altrimenti stringa vuota.
    """
    try:
        v = yf.Ticker(normalizza_ticker(ticker)).isin
        if v and isinstance(v, str) and len(v) >= 12 and v != "-":
            return v
    except Exception:
        pass
    return ""


# ---------------------------------------------------------------------------
# Dati OHLCV per l'analisi tecnica (candele, volumi, medie mobili)
# ---------------------------------------------------------------------------

def scarica_ohlcv(ticker: str, period: str = "max") -> pd.DataFrame:
    """Scarica i dati OHLCV (Open/High/Low/Close/Volume) di un singolo asset.

    Pensato per l'analisi tecnica: prezzi aggiustati (``auto_adjust=True``) e
    valuta **nativa** dell'asset (nessuna conversione). Si scarica di default
    tutto lo storico (``period="max"``) e poi si ritaglia l'intervallo a video.
    Indice senza fuso orario. In caso di errore ritorna un DataFrame vuoto.
    """
    try:
        tk = yf.Ticker(normalizza_ticker(ticker))
        hist = tk.history(period=period, auto_adjust=True)
        if hist is None or hist.empty:
            return pd.DataFrame()
        if isinstance(hist.index, pd.DatetimeIndex) and hist.index.tz is not None:
            hist.index = hist.index.tz_localize(None)
        hist.index = hist.index.normalize()
        colonne = [c for c in ["Open", "High", "Low", "Close", "Volume"] if c in hist.columns]
        return hist[colonne]
    except Exception:
        return pd.DataFrame()
