# 📊 Sharpe — Analisi ETF / Indici e Portafoglio

Strumento locale e interattivo (Streamlit) per analizzare singoli ETF/indici e
un portafoglio composto da essi: rendimenti, rischio, correlazioni,
diversificazione e distribuzione per paese/settore.

> ⚠️ **Disclaimer**: strumento a scopo di **analisi e didattico**. Non
> costituisce consulenza finanziaria né raccomandazione di investimento.
> I dati provengono da Yahoo Finance (via `yfinance`) e possono contenere
> errori, ritardi o lacune.

---

## Funzionalità

L'app è divisa in due sezioni (menu a lato):

- **🧱 Builder** — costruzione e analisi del portafoglio.
- **📈 Analisi tecnica** — per ogni asset: grafico a **candele**, **volumi**,
  **medie mobili** e **RSI**, strumenti per **disegnare linee/trendline**,
  statistiche principali e selettore di intervallo (YTD / 1A / 3A / 5A / 10A / max).

- **Ricerca online e costruzione del portafoglio nell'app**: cerca ETF/indici
  per nome o ticker (dati da Yahoo Finance), selezionali e assegna i pesi.
  Gli asset sono mostrati con il loro **nome reale**, non con il ticker.
- **Singoli asset**: rendimento annualizzato (CAGR), volatilità annualizzata,
  Sharpe, Sortino, max drawdown, rendimento cumulato; grafico dell'andamento
  normalizzato a 100 e grafico dei drawdown.
- **Portafoglio**: metriche complessive con volatilità calcolata dalla
  **matrice di covarianza** (σₚ = √(wᵀ Σ w)), confronto portafoglio vs singoli
  asset, **heatmap di correlazione** e **contributo di ciascun asset al rischio**.
- **Allocazione**: distribuzione percentuale per **paese** e per **settore**,
  con recupero automatico dei settori da yfinance (dove disponibile) e/o
  inserimento manuale / da CSV.
- **Ottimizzazione (extra)**: pesi ottimali secondo tre obiettivi —
  **minima varianza**, **massimo rendimento annuo** e **massimo indice di
  Sharpe** (portafoglio di tangenza) — con **frontiera efficiente** e pulsante
  per applicare i pesi ottimali al portafoglio (richiede `scipy`).
  Una **quota minima per asset** (slider, % della quota equipesata: la soglia
  è L = α·1/N) garantisce che nessun asset finisca a 0% e si scala col numero
  di asset restando sempre ammissibile.
- **Salva/carica** un portafoglio in formato JSON.
- **Conversione valutaria** opzionale: tutti i prezzi convertiti nella valuta
  base (default EUR) usando i tassi di cambio di yfinance, *prima* di calcolare
  i rendimenti.

## Struttura del progetto

```
Sharpe/
├── data.py                 # download e pulizia dati (prezzi, cambi, settori, OHLCV, ricerca)
├── metrics.py              # calcoli (rendimenti, rischio, correlazioni, ottimizzazione, indicatori tecnici)
├── common.py               # stato/funzioni condivise + barra laterale (parametri)
├── app.py                  # punto d'ingresso: configura e gestisce la navigazione tra le pagine
├── page_builder.py         # pagina "Builder": costruzione e analisi del portafoglio
├── page_analisi.py         # pagina "Analisi tecnica": candele, volumi, medie mobili, RSI
├── requirements.txt        # dipendenze
├── sample_composition.csv  # esempio di composizione paese/settore (valori illustrativi)
└── README.md
```

## Requisiti

- Python **3.11+**
- I pacchetti elencati in `requirements.txt`
  (`yfinance`, `pandas`, `numpy`, `plotly`, `streamlit`, `scipy`)
- Connessione a Internet (i dati vengono scaricati da Yahoo Finance)

## Installazione

```bash
# (consigliato) crea un ambiente virtuale
python -m venv .venv
# Windows
.venv\Scripts\activate
# macOS / Linux
source .venv/bin/activate

# installa le dipendenze
pip install -r requirements.txt
```

## Avvio

```bash
streamlit run app.py
```

Si aprirà il browser su `http://localhost:8501`.

## Come si usa

1. Nella sezione **🔎 Cerca e aggiungi ETF / indici** scrivi un nome o un
   ticker (es. `MSCI World`, `S&P 500`, `obbligazioni globali`, `SWDA`) e premi
   **Cerca**: i risultati arrivano da Yahoo Finance (gli ETF/indici sono messi
   in cima). Premi **➕ Aggiungi** sull'asset desiderato.
   - La ricerca per nome può restituire lo stesso ETF su più borse/valute:
     scegli la quotazione che preferisci guardando il ticker (suffisso di
     borsa: `.MI` Milano, `.DE` Xetra, `.AS` Amsterdam, `.L` Londra, `.SW`
     Svizzera, `.MC` Madrid…). Senza suffisso (es. `SPY`, `VOO`) è la borsa USA.
2. Nella tabella **📋 Portafoglio** imposta i **pesi %** di ciascun asset
   (oppure premi **⚖️ Equipesati**); con **🗑** rimuovi un asset. I pesi
   vengono normalizzati a 100% per i calcoli.
3. Nella **barra laterale** scegli un **periodo rapido** (es. `5y`) o un
   **intervallo personalizzato**, il **tasso risk-free** annuo (default 3%) e
   la **valuta base** (default EUR); attiva/disattiva la **conversione
   valutaria**.
4. Esplora le tab: l'analisi si aggiorna automaticamente. Gli asset sono
   mostrati con il loro **nome reale** (il ticker è usato solo per scaricare i
   dati). Usa **🔄 Aggiorna dati** nella sidebar per forzare un nuovo download.

### Composizione paese/settore

La composizione (holdings) **non** è ricavabile dai prezzi. Nella tab
**Allocazione** puoi:

- premere **🔄 Recupera settori da yfinance** (spesso non disponibile per ETF
  UCITS europei);
- **caricare un CSV** con la composizione (vedi `sample_composition.csv`);
- **modificarla a mano** nella tabella.

Formato CSV atteso:

```csv
ticker,tipo,categoria,peso
SWDA.MI,paese,Stati Uniti,0.71
SWDA.MI,settore,Tecnologia,0.24
...
```

- `tipo` ∈ {`paese`, `settore`}
- `peso` in frazione (`0.24`) o in percentuale (`24`): se la somma per
  (ticker, tipo) supera 1.5, i valori vengono interpretati come percentuali.

> I valori in `sample_composition.csv` sono **illustrativi**: per analisi reali
> usa i dati dal KID/factsheet dell'emittente.

## Note sui calcoli

- Si lavora sui **rendimenti giornalieri semplici**, annualizzati con **252**
  giorni di borsa.
- Le serie vengono **allineate** sull'intervallo di date comune a tutti gli
  asset; i buchi interni (festività di borsa diverse) sono riempiti in avanti.
- I prezzi usano i **close aggiustati** (dividendi e split) — ottica *total return*.
- La volatilità di portafoglio è calcolata dalla covarianza annualizzata,
  **non** come media pesata delle volatilità.
- Il **contributo al rischio** di un asset = contributo marginale × peso, in %
  sul totale: evidenzia chi diversifica e chi pesa davvero sul rischio.

## Limiti noti

- La disponibilità e la qualità dei dati dipendono da Yahoo Finance.
- I dati di settore via yfinance sono spesso assenti per gli ETF europei.
- La conversione valutaria usa il cambio di chiusura giornaliero (approssimazione).
- Nessuna garanzia sull'accuratezza: **uso didattico**.
