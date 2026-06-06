# 📊 Sharpe — Analisi ETF / Indici e Portafoglio

Strumento interattivo (Streamlit) per analizzare singoli ETF/indici e un
portafoglio composto da essi: rendimenti, rischio, correlazioni,
diversificazione, distribuzione per paese/settore, analisi tecnica, indicatori
statistici e confronto con portafogli celebri. Funziona in locale e online
(Streamlit Community Cloud).

> ⚠️ **Disclaimer**: strumento a scopo di **analisi e didattico**. Non
> costituisce consulenza finanziaria né raccomandazione di investimento.
> I dati provengono da Yahoo Finance (via `yfinance`) e possono contenere
> errori, ritardi o lacune.

---

## Funzionalità

In cima all'app, sempre visibile, c'è l'**indicatore generale di mercato
risk-on / risk-off (1–5)**: stima statistica, indipendente dal portafoglio, se
il contesto favorisca più gli asset rischiosi (azioni) o quelli prudenti
(obbligazioni/liquidità), su orizzonte orientativo di ~1 anno (calcolato su un
benchmark azionario globale).

L'app è divisa in due sezioni (menu a lato):

### 🧱 Builder — costruzione e analisi del portafoglio
- **Ricerca online**: cerca ETF/indici per nome o ticker (dati da Yahoo
  Finance), selezionali e assegna i pesi. Gli asset sono mostrati con il loro
  **nome reale**, non con il ticker.
- **Singoli asset**: CAGR, volatilità, Sharpe, Sortino, max drawdown, rendimento
  cumulato; andamento normalizzato a 100 e grafico dei drawdown.
- **Portafoglio**: metriche complessive con volatilità dalla **matrice di
  covarianza** (σₚ = √(wᵀ Σ w)), confronto portafoglio vs singoli asset,
  **heatmap di correlazione** e **contributo di ciascun asset al rischio**.
- **Allocazione**: distribuzione per **paese** e **settore** (recupero settori
  da yfinance dove disponibile e/o inserimento manuale / da CSV).
- **⏱️ Timing** (rolling returns): per ogni giorno di partenza, quanto avrebbe
  reso il portafoglio **in % all'anno** tenendolo per una finestra fissa
  (1 / 3 / 5 / 10 anni). Mostra quanto conta il momento d'ingresso, con
  peggiore/mediana/migliore e % di finestre positive. Usa tutto lo storico.
- **📊 Statistica**: indicatori del portafoglio — prezzo vs media storica
  (caro/economico), RSI, vantaggio statistico (Sharpe + % di anni positivi).
- **🧮 Ottimizzazione**: pesi ottimali per tre obiettivi — **minima varianza**,
  **massimo rendimento annuo**, **massimo Sharpe** (tangenza) — con **frontiera
  efficiente** e pulsante per applicare i pesi (richiede `scipy`). Una **quota
  minima per asset** (slider, % della quota equipesata: L = α·1/N) evita che un
  asset vada a 0% e resta sempre ammissibile al variare del numero di asset.
- **🆚 Confronto**: confronta il tuo portafoglio (grafico base 100 + tabella di
  statistiche) con singoli ETF/indici e con **portafogli famosi** (60/40, All
  Weather, Golden Butterfly, Permanent Portfolio), ricostruiti con ETF proxy.

### 📈 Analisi tecnica (per singolo asset)
- Grafico a **candele** (OHLC), **volumi**, **medie mobili** SMA/EMA con periodi
  a scelta, **RSI** con periodo regolabile, strumenti per **disegnare
  linee/trendline**.
- **Statistiche** dell'asset e **indicatori** (caro/economico, RSI, vantaggio
  statistico) sull'intervallo selezionato (YTD / 1A / 3A / 5A / 10A / max).
- I prezzi usano la **valuta nativa** dell'asset (standard per le candele).

### Trasversali
- **Salva/carica** un portafoglio in formato JSON.
- **Conversione valutaria** opzionale: prezzi convertiti nella valuta base
  (default EUR) coi tassi di cambio di yfinance, *prima* di calcolare i rendimenti.
- Auto-reload locale (`.streamlit/config.toml`, `runOnSave`).

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
# in alternativa, se "streamlit" non è nel PATH:
python -m streamlit run app.py
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
4. Esplora le tab del **Builder** (Singoli asset, Portafoglio, Allocazione,
   Timing, Statistica, Ottimizzazione, Confronto): l'analisi si aggiorna
   automaticamente. Gli asset sono mostrati con il loro **nome reale** (il
   ticker è usato solo per scaricare i dati). Usa **🔄 Aggiorna dati** nella
   sidebar per forzare un nuovo download.
5. Passa alla pagina **📈 Analisi tecnica** (menu a lato) per il dettaglio di un
   singolo asset (candele, volumi, medie mobili, RSI, disegno trendline).
6. In cima a ogni pagina trovi l'**indicatore di mercato risk-on/off**:
   apri il pannello per vedere il gauge 1–5 e i tre segnali che lo compongono.

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

## Indicatori statistici (metodologia)

> ⚠️ Sono indicatori **statistici/storici a scopo didattico**, non consigli di
> investimento. I rendimenti passati non predicono quelli futuri.

- **Semaforo di mercato (risk-on/off, 1–5)**: media di tre segnali normalizzati
  in [−1, +1] su un benchmark azionario globale — **trend** (prezzo vs media
  200gg), **regime di volatilità** (volatilità recente vs sua mediana storica),
  **momentum** (~6 mesi). Il composito è mappato su 1–5 (1–2 rosso = meglio asset
  prudenti, 3 grigio = neutro, 4–5 verde = meglio asset rischiosi).
- **Prezzo caro/economico**: confronto del livello attuale con la propria media
  mobile (z-score). z > +2 ≈ "molto caro", z < −2 ≈ "molto economico". È una
  lettura *statistica*, non una valutazione fondamentale del valore reale.
- **RSI (14)**: > 70 ipercomprato, < 30 ipervenduto.
- **Vantaggio statistico**: sintesi di Sharpe storico e quota di finestre di
  1 anno chiuse in positivo (giudizio favorevole / neutro / sfavorevole).
- **Timing (rolling returns)**: per ogni data di partenza, CAGR su una finestra
  fissa (1/3/5/10 anni) a partire dall'indice di ricchezza del portafoglio.
- **Confronto portafogli famosi**: ricostruiti con ETF proxy USA (es. All
  Weather ≈ 30% azioni, 55% obbligazioni, 7,5% oro, 7,5% materie prime); le serie
  sono allineate sul periodo comune e (se attiva) convertite nella valuta base.

## Online (Streamlit Community Cloud)

L'app può essere pubblicata gratuitamente su Streamlit Community Cloud a partire
da un repository GitHub: il file principale è `app.py`. Ad ogni `commit` sul
repo l'app online si ricostruisce automaticamente. Consigliata la versione di
**Python 3.13** nelle impostazioni dell'app.

## Limiti noti

- La disponibilità e la qualità dei dati dipendono da Yahoo Finance (possibili
  ritardi, lacune o limiti di frequenza delle richieste).
- I dati di settore via yfinance sono spesso assenti per gli ETF europei.
- La conversione valutaria usa il cambio di chiusura giornaliero (approssimazione).
- Il grafico **Timing** richiede storico più lungo della finestra scelta: con
  ETF giovani le finestre lunghe (5/10 anni) possono avere pochi o zero punti.
- I **portafogli famosi** usano ETF proxy in USD: utili per confronto relativo,
  non repliche esatte.
- Gli **indicatori statistici** sono euristici e a scopo didattico.
- Nessuna garanzia sull'accuratezza: **uso didattico**, non consulenza finanziaria.
