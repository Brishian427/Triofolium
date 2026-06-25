# Trifolium

Local execution layer for the MOMQ competition workflow.

## Setup

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

Create `.env` locally. Do not commit it.

```text
MT5_LOGIN=
MT5_PASSWORD=
MT5_SERVER=
```

## Task 01 L0/L1 Smoke Test

```powershell
.\.venv\Scripts\python.exe scripts\smoke_test_mt5.py
```

The smoke test loads credentials from `.env`, initializes MT5, prints sanitized
terminal/account information, checks XAUUSD tick and M1 candles, and verifies
the 15 configured competition instruments.

## Task 01 L2 Calibration

This places a real order and must only be run under principal supervision.
The script refuses to run unless `MT5_CALIBRATION_MODE=1` is present in the
environment.

```powershell
$env:MT5_CALIBRATION_MODE = "1"
.\.venv\Scripts\python.exe scripts\calibration_trade.py --symbol AUDUSD --lots 0.01 --mode ping_pong
```
