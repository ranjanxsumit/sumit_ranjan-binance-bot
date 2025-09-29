# Binance Futures Order Bot

A command-line trading assistant for the Binance USDT-M Futures **testnet**. The bot supports validated market and limit orders, a TWAP (Time-Weighted Average Price) execution strategy, structured logging, and a friendly CLI summary.

> **Warning**: This project is configured for the Binance Futures **testnet**. Never plug real credentials into a test build, and always review orders before running them on mainnet.

## Features

- ✅ Market and limit orders with input validation.
- ✅ AWS-style structured logging to `bot.log` (rotating file + console).
- ✅ TWAP strategy that splits a large order into evenly sized slices.
- ✅ Consistent CLI summaries with optional raw JSON output.
- ✅ Interactive console mode with live Fear & Greed and trade statistics.
- ✅ Streamlit dashboard for a lightweight point-and-click frontend.
- ✅ Exchange info pre-flight cache to guard against unsupported symbols.
- ✅ Automatic timestamp resync to combat Binance `-1021` drift errors.
- ✅ Sentiment advisor driven by local CSV datasets powering CLI + Streamlit defaults.
- 🧪 Ready for extension with Stop-Limit, OCO, and Grid strategies.

## Requirements

- Python 3.10 or newer
- Binance Testnet Futures account with generated API key and secret
- Recommended: virtual environment (``venv`` or ``conda``)

Install dependencies:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

## Configuration

Export your API credentials as environment variables **before** running the bot:

```powershell
$env:BINANCE_API_KEY="<your_testnet_api_key>"
$env:BINANCE_API_SECRET="<your_testnet_api_secret>"
```

Optional overrides:

- `BINANCE_TESTNET` – Set to `false` to target mainnet (not recommended without thorough testing).
- `BINANCE_RECV_WINDOW` – Custom receive window in milliseconds (default `5000`).
- `BINANCE_BASE_URL` – Override base REST URL (advanced use).

## Quick Start

After completing the installation and configuration steps above, you can start using the bot with these simple commands:

1. **Activate your virtual environment:**
   ```powershell
   .\.venv\Scripts\Activate.ps1
   ```

2. **Start the interactive console (recommended for beginners):**
   ```powershell
   python -m src.cli interactive
   ```

3. **Or launch the Streamlit dashboard:**
   ```powershell
   streamlit run src/ui/streamlit_app.py
   ```

The interactive console provides guided order placement with real-time market sentiment, while the Streamlit dashboard offers a web-based interface for the same functionality.

## Usage

Activate the virtual environment and run the CLI. The examples below assume Windows PowerShell.

### Market Order

```powershell
python -m src.cli market BTCUSDT BUY 0.01
```

### Limit Order

```powershell
python -m src.cli limit BTCUSDT SELL 0.05 92000 --time-in-force GTC
```

### TWAP Strategy (5 slices, every 20 seconds)

```powershell
python -m src.cli twap BTCUSDT BUY 0.25 5 --interval 20 --order-type MARKET
```

Add `--raw-json` to print the raw API payload instead of the friendly summary. Use `--log-file` if you prefer another log destination.

### Interactive Console (enhanced CLI)

```powershell
python -m src.cli interactive
```

The interactive mode displays the latest Fear & Greed index and a snapshot of historical trades sourced from `fear_greed_index.csv` and `historical_data.csv`. It then walks you through market, limit, or TWAP order placement with inline validation.

Real-time sentiment cues prefill suggested side, quantity, and price targets based on the CSV insights.

### Streamlit Dashboard (lightweight frontend)

```powershell
streamlit run src/ui/streamlit_app.py
```

The dashboard surfaces the same data insights, offers tabbed forms for market/limit/TWAP orders, and reuses the core bot implementation. Provide your Binance credentials via environment variables before launching; Streamlit will alert you if they are missing.

The sidebar recomputes a sentiment signal each refresh and threads the recommended symbol, side, and sizing directly into the order forms.

## Logging

All activity is appended to `bot.log` with timestamps and severity levels. Logs are rotated at 5MB with up to three backups retained.

## Project Structure

```
project_root/
├── bot.log              # Structured logs (rotating file)
├── README.md            # Setup & usage guide
├── report.pdf           # Implementation summary
├── requirements.txt     # Python dependencies
└── src/
    ├── advanced/
    │   └── twap.py              # TWAP strategy implementation
    ├── core/
    │   ├── binance_client.py
    │   ├── bot.py
    │   ├── config.py
    │   ├── logger.py
    │   └── validators.py
    ├── data/
    │   ├── __init__.py
    │   └── feeds.py             # Fear & Greed + historical trade loaders
    ├── orders/
    │   ├── base.py
    │   ├── limit_orders.py
    │   └── market_orders.py
    ├── ui/
    │   ├── __init__.py
    │   └── streamlit_app.py     # Lightweight dashboard
    └── cli.py                   # CLI + interactive mode
```

## Testing & Extensibility

- For dry runs without hitting the API, wrap the executors or mock the `Client` object.
- Extend `src/advanced/` with additional strategies (Stop-Limit, OCO, Grid, etc.).
- Integrate external signals (e.g., Fear & Greed index) by enriching the CLI before order execution (starter hooks provided in `src/data/feeds.py`).

### Running Tests

```powershell
pytest
```

## Troubleshooting

| Symptom | Likely Cause | Fix |
|---|---|---|
| `BINANCE_API_KEY must be set` | Missing environment variables | Set `BINANCE_API_KEY` and `BINANCE_API_SECRET` before running |
| `Timestamp for this request is outside of the recvWindow.` (`-1021`) | Local clock drift relative to Binance | The bot now auto-resyncs before retrying; if it persists, ensure your system clock is synced and consider increasing `BINANCE_RECV_WINDOW`. |
| `-2019 margin` or quantity errors | Lot size / leverage mismatch | Check exchange filters via the Binance UI or API |
| CLI exits with `Validation error` | Invalid symbol/side/price format | Use uppercase symbols and numeric quantities |

## Next Steps

- Add Stop-Limit and OCO executors under `src/advanced/`.
- Capture websocket fills in a separate async worker.
- Enrich CLI with colorized output (e.g., `rich` library) and interactive prompts.

Happy testing and safe trading!
