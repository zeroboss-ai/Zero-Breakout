# ZeroBreakout — Stock Pattern Scanner for NSE India 📈

**ZeroBreakout** is a clean, minimal stock pattern scanner built for NSE-listed Indian stocks. Inspired by Zerodha's minimalist design philosophy, it scans stocks daily after market close (~3:30–4:00 PM IST), detects high-probability breakout patterns, and presents setups in a fast, mobile-first interface.

---

## Key Features

- **Daily NSE Bhavcopy & Historical Pipeline**: Automatically stores 5+ years of daily OHLCV in `price_history` and maintains lifetime All-Time Highs in `stocks`.
- **Precomputed Signal Caching**: Pattern detection runs post-market in the background and writes to `signals`. The website reads only precomputed signals and history for instantaneous sub-millisecond response.
- **Zerodha-Inspired Minimalist UI**:
  - **Tab 1 (Scanner)**: Search bar, pattern filter chips, clean rows showing strictly the stock symbol on the left and pattern badge on the right.
  - **Tab 2 (Setup)**: Stock name, sector, live price & % change in Zerodha green/red, 1M/6M/1Y/5Y candlestick chart with 20 SMA & 50 SMA overlay line, pivot line, stats card, and Gemini AI technical breakdown.
  - **Tab 3 (Watchlist)**: Starred stocks list with instant inline remove.
  - **Tab 4 (Account)**: Trader profile, ZeroBreakout Pro tier preview, settings, and pattern cheat sheet.
- **Modular Pattern Detection Engine (`backend/patterns/`)**:
  - `All-Time High Breakout` (Full history ATH pivot)
  - `52-Week High Breakout` (Trailing 252-day high)
  - `52-Week Low Breakdown` (Trailing 252-day low)
  - `Range Breakout` (Tight consolidation range with volume surge)
  - `Double Bottom (W Pattern)` (Neckline pivot breakout)
  - `VCP` (Mark Minervini Volatility Contraction Pattern)
  - `Cup and Handle` (Rounded base with handle breakout)
  - `MA Crossover` (Bullish 20/50 SMA and Golden Cross)
- **Extensible Architecture**: Add any new pattern by simply creating a class inheriting from `BasePatternDetector`.

---

## Tech Stack

- **Backend**: Python 3.11+, FastAPI, SQLite (WAL mode), APScheduler
- **AI Synthesis**: Google Gemini API (`gemini-2.5-flash`)
- **Frontend**: Vanilla HTML5, Modern CSS3 (Zerodha Design System), Canvas Candlestick & Moving Average Chart
- **Deployment**: Render Web Service (`render.yaml`, `Procfile`)

---

## Local Development Setup

1. **Install dependencies**:
   ```bash
   pip install -r requirements.txt
   ```

2. **Run Server**:
   ```bash
   uvicorn backend.main:app --reload --port 8000
   ```

3. **Open in Browser**:
   Navigate to `http://localhost:8000`

---

## Render Cloud Deployment

ZeroBreakout is configured with `render.yaml` and `Procfile`.
Simply connect your GitHub repository to Render and deploy as a Web Service.
