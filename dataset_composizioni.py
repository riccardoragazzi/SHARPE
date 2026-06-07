"""
dataset_composizioni.py
=======================
Dataset INTERNO con la ripartizione **geografica (paese)** e **settoriale**
approssimata dei principali ETF/indici usati da un investitore passivo
(soprattutto UCITS quotati in Europa). Serve a popolare automaticamente la tab
"Allocazione" anche quando yfinance non espone gli holdings.

⚠️ Sono **stime indicative** ricavate dai factsheet/KID (valori che cambiano nel
tempo): vanno bene per capire la diversificazione di massima, non sono la
composizione esatta e aggiornata. L'utente può comunque sovrascrivere a mano o
via CSV.

Struttura:
- ``COMPOSIZIONI``: chiave "canonica" -> {"paese": {cat: %}, "settore": {cat: %}}
- ``TICKER_MAP`` / ``ISIN_MAP``: molti ticker/ISIN (stesso fondo su borse diverse)
  puntano alla stessa composizione canonica.
"""

from __future__ import annotations

# --- Composizioni canoniche (percentuali indicative) -----------------------

COMPOSIZIONI: dict[str, dict[str, dict[str, float]]] = {
    # Azionario sviluppato mondiale (MSCI World)
    "MSCI_WORLD": {
        "paese": {"Stati Uniti": 71, "Giappone": 6, "Regno Unito": 4, "Francia": 3,
                  "Canada": 3, "Svizzera": 3, "Germania": 2.5, "Australia": 2,
                  "Paesi Bassi": 1.5, "Altri": 4},
        "settore": {"Tecnologia": 25, "Servizi finanziari": 15, "Sanità": 11,
                    "Consumi ciclici": 11, "Industriali": 11, "Servizi di comunicazione": 8,
                    "Consumi difensivi": 6, "Energia": 4, "Materiali di base": 4,
                    "Utility": 2.5, "Immobiliare": 2.5},
    },
    # Azionario mondiale sviluppato + emergenti (FTSE All-World / MSCI ACWI)
    "ALL_WORLD": {
        "paese": {"Stati Uniti": 60, "Giappone": 6, "Regno Unito": 3.5, "Cina": 3,
                  "Canada": 3, "Francia": 2.5, "Svizzera": 2.5, "Germania": 2,
                  "India": 2, "Taiwan": 2, "Altri": 13.5},
        "settore": {"Tecnologia": 24, "Servizi finanziari": 16, "Sanità": 10,
                    "Consumi ciclici": 11, "Industriali": 11, "Servizi di comunicazione": 8,
                    "Consumi difensivi": 6, "Energia": 4.5, "Materiali di base": 4.5,
                    "Utility": 2.5, "Immobiliare": 2},
    },
    # Azionario USA (S&P 500)
    "SP500": {
        "paese": {"Stati Uniti": 100},
        "settore": {"Tecnologia": 31, "Servizi finanziari": 13, "Sanità": 12,
                    "Consumi ciclici": 10, "Servizi di comunicazione": 9, "Industriali": 9,
                    "Consumi difensivi": 6, "Energia": 4, "Immobiliare": 2.5,
                    "Materiali di base": 2.5, "Utility": 2.5},
    },
    # Azionario USA tecnologico (Nasdaq 100)
    "NASDAQ100": {
        "paese": {"Stati Uniti": 97, "Altri": 3},
        "settore": {"Tecnologia": 50, "Servizi di comunicazione": 16, "Consumi ciclici": 13,
                    "Consumi difensivi": 6, "Sanità": 6, "Industriali": 5, "Utility": 1,
                    "Materiali di base": 1, "Servizi finanziari": 2},
    },
    # Azionario emergenti (MSCI/FTSE Emerging)
    "EMERGING": {
        "paese": {"Cina": 27, "India": 18, "Taiwan": 18, "Corea del Sud": 12, "Brasile": 5,
                  "Arabia Saudita": 4, "Sudafrica": 3, "Altri": 13},
        "settore": {"Tecnologia": 23, "Servizi finanziari": 22, "Consumi ciclici": 13,
                    "Servizi di comunicazione": 9, "Materiali di base": 8, "Industriali": 6,
                    "Consumi difensivi": 5, "Energia": 5, "Sanità": 4, "Utility": 3,
                    "Immobiliare": 2},
    },
    # Azionario Europa (MSCI Europe / STOXX 600)
    "EUROPE": {
        "paese": {"Regno Unito": 22, "Francia": 17, "Svizzera": 15, "Germania": 12,
                  "Paesi Bassi": 6, "Svezia": 5, "Italia": 4, "Spagna": 4, "Danimarca": 4,
                  "Altri": 11},
        "settore": {"Servizi finanziari": 18, "Sanità": 15, "Industriali": 14,
                    "Consumi difensivi": 12, "Consumi ciclici": 10, "Tecnologia": 8,
                    "Materiali di base": 8, "Energia": 5, "Servizi di comunicazione": 4,
                    "Utility": 4, "Immobiliare": 2},
    },
    # Obbligazionario globale aggregato (Global Aggregate)
    "GLOBAL_AGG_BOND": {
        "paese": {"Stati Uniti": 40, "Giappone": 11, "Cina": 8, "Francia": 6, "Germania": 5,
                  "Regno Unito": 5, "Italia": 4, "Canada": 3, "Altri": 18},
        "settore": {"Titoli di Stato": 55, "Corporate": 20, "Agenzie e sovranazionali": 15,
                    "Cartolarizzati": 10},
    },
    # Obbligazionario governativo Euro
    "EUR_GOVT_BOND": {
        "paese": {"Francia": 24, "Italia": 22, "Germania": 18, "Spagna": 14, "Belgio": 6,
                  "Paesi Bassi": 6, "Austria": 4, "Altri": 6},
        "settore": {"Titoli di Stato": 100},
    },
    # Obbligazionario governativo USA (Treasury)
    "US_TREASURY": {
        "paese": {"Stati Uniti": 100},
        "settore": {"Titoli di Stato": 100},
    },
    # Obbligazionario corporate Euro
    "EUR_CORP_BOND": {
        "paese": {"Francia": 20, "Stati Uniti": 18, "Germania": 12, "Paesi Bassi": 9,
                  "Regno Unito": 8, "Spagna": 7, "Italia": 6, "Altri": 20},
        "settore": {"Corporate": 100},
    },
    # Oro fisico
    "GOLD": {
        "paese": {"Globale (oro)": 100},
        "settore": {"Oro / Materie prime": 100},
    },
}

# --- Mappa ticker (più borse) -> composizione canonica ----------------------

TICKER_MAP: dict[str, str] = {
    # MSCI World
    "SWDA.MI": "MSCI_WORLD", "IWDA.AS": "MSCI_WORLD", "IWDA.L": "MSCI_WORLD",
    "SWDA.L": "MSCI_WORLD", "EUNL.DE": "MSCI_WORLD", "XDWD.DE": "MSCI_WORLD",
    "URTH": "MSCI_WORLD", "SWLD.SW": "MSCI_WORLD",
    # All-World (dev + emergenti)
    "VWCE.DE": "ALL_WORLD", "VWCE.MI": "ALL_WORLD", "VWRL.AS": "ALL_WORLD",
    "VWRL.L": "ALL_WORLD", "VWRA.L": "ALL_WORLD", "ACWI": "ALL_WORLD",
    "SPYI.DE": "ALL_WORLD", "ISAC.L": "ALL_WORLD",
    # S&P 500
    "CSPX.MI": "SP500", "CSSPX.MI": "SP500", "SXR8.DE": "SP500", "VUAA.DE": "SP500",
    "VUAA.MI": "SP500", "VUSA.MI": "SP500", "SPY5.MI": "SP500", "P500.MI": "SP500",
    "IVV": "SP500", "VOO": "SP500", "SPY": "SP500", "^GSPC": "SP500",
    # Nasdaq 100
    "EQQQ.MI": "NASDAQ100", "EQQQ.DE": "NASDAQ100", "CSNDX.MI": "NASDAQ100",
    "SXRV.DE": "NASDAQ100", "QQQ": "NASDAQ100", "^NDX": "NASDAQ100",
    # Emergenti
    "EIMI.MI": "EMERGING", "EIMI.L": "EMERGING", "EMIM.AS": "EMERGING",
    "IS3N.DE": "EMERGING", "XMME.DE": "EMERGING", "VFEM.L": "EMERGING",
    # Europa
    "IMEU.MI": "EUROPE", "MEUD.PA": "EUROPE", "EXSA.DE": "EUROPE", "VEUR.MI": "EUROPE",
    "SMEA.MI": "EUROPE",
    # Obbligazionario globale aggregato
    "AGGH.MI": "GLOBAL_AGG_BOND", "AGGH.L": "GLOBAL_AGG_BOND", "AGGG.L": "GLOBAL_AGG_BOND",
    "EUNA.DE": "GLOBAL_AGG_BOND", "VAGF.MI": "GLOBAL_AGG_BOND", "VAGF.DE": "GLOBAL_AGG_BOND",
    "AGG": "GLOBAL_AGG_BOND", "BND": "GLOBAL_AGG_BOND",
    # Governativi Euro
    "IEGA.MI": "EUR_GOVT_BOND", "SEGA.DE": "EUR_GOVT_BOND", "VGEA.MI": "EUR_GOVT_BOND",
    "EGOV.MI": "EUR_GOVT_BOND",
    # Treasury USA
    "IDTL.MI": "US_TREASURY", "TLT": "US_TREASURY", "IEI": "US_TREASURY", "SHY": "US_TREASURY",
    # Corporate Euro
    "IEAC.MI": "EUR_CORP_BOND", "VECP.MI": "EUR_CORP_BOND",
    # Oro
    "SGLD.MI": "GOLD", "IGLN.L": "GOLD", "4GLD.DE": "GOLD", "PHAU.MI": "GOLD",
    "SGLD.L": "GOLD", "GLD": "GOLD",
}

# --- Mappa ISIN -> composizione canonica (per i fondi più comuni) -----------

ISIN_MAP: dict[str, str] = {
    "IE00B4L5Y983": "MSCI_WORLD",   # iShares Core MSCI World
    "IE00BK5BQT80": "ALL_WORLD",    # Vanguard FTSE All-World (VWCE)
    "IE00B3RBWM25": "ALL_WORLD",    # Vanguard FTSE All-World (VWRL)
    "IE00B5BMR087": "SP500",        # iShares Core S&P 500 (CSPX)
    "IE00BFY0GT14": "SP500",        # SPDR S&P 500 (SPY5)
    "IE00B3WJKG14": "NASDAQ100",    # iShares Nasdaq 100
    "IE00BFMXXD54": "NASDAQ100",    # Invesco EQQQ Nasdaq 100
    "IE00BKM4GZ66": "EMERGING",     # iShares Core MSCI EM IMI (EIMI)
    "IE00B4K48X80": "EUROPE",       # iShares Core MSCI Europe
    "IE00BDBRDM35": "GLOBAL_AGG_BOND",  # iShares Core Global Aggregate Bond (AGGH)
    "IE00B4WXJJ64": "EUR_GOVT_BOND",    # iShares Core Euro Govt Bond
    "IE00B3F81R35": "EUR_CORP_BOND",    # iShares Core Euro Corp Bond
}


def _percentuali_a_frazioni(d: dict[str, float]) -> dict[str, float]:
    """Normalizza un dizionario di percentuali a frazioni che sommano a 1."""
    tot = sum(d.values())
    if tot <= 0:
        return {}
    return {k: v / tot for k, v in d.items()}


def composizione_nota(ticker: str, isin: str | None = None) -> dict[str, dict[str, float]]:
    """Restituisce la composizione nota (paese/settore in frazioni) per un asset.

    Cerca prima per **ticker** (maiuscolo), poi per **ISIN**. Se non trovata,
    ritorna ``{}``.
    """
    chiave = TICKER_MAP.get(str(ticker).strip().upper())
    if not chiave and isin:
        chiave = ISIN_MAP.get(str(isin).strip().upper())
    if not chiave:
        return {}
    comp = COMPOSIZIONI[chiave]
    return {
        "paese": _percentuali_a_frazioni(comp.get("paese", {})),
        "settore": _percentuali_a_frazioni(comp.get("settore", {})),
    }
