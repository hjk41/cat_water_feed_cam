# AGENTS.md

## Cursor Cloud specific instructions

### Project Overview
Smart Cat Water Feeder — IoT project with a Python Flask server (AI-powered cat detection via PaddleClas + Xiaomi thermometer dashboard) and ESP32-CAM firmware. Only the **Flask server** (`server/`) is testable in software; the ESP32 hardware side is simulated via test scripts.

### Running the Server
```bash
source .venv/bin/activate
cd server && python app.py
```
Server starts on port **8099**. Key pages/endpoints:
- `POST /detect`, `GET /log`, `POST /toggle_brightness`, `GET /brightness_status` — cat detection (see `readme.md`)
- `GET /thermometers` — Xiaomi temperature/humidity dashboard (auto-refreshes every 10s)
- `GET /api/thermometers` — JSON API for sensor readings

### Running Tests
- **Integration test** (requires running server): `cd server && python test/test.py` — sends all test JPGs to `/detect`.
- **Unit/model tests**: `cd server && python test/quick_test.py` — tests multiple PaddleClas models directly. Note: these tests load multiple large models and may fail with `std::bad_alloc` in memory-constrained environments.
- **Thermometer unit tests**: `cd server && python test/test_xiaomi_thermo.py -v` — tests XiaomiThermoService with mocked cloud clients (RPC, MIoT fallback, missing credentials).

### Xiaomi Thermometer Dashboard
The `/thermometers` page requires environment variables to connect to Xiaomi IoT cloud:
- `MIIO_USERNAME` — Xiaomi account email/phone
- `MIIO_PASSWORD` — Xiaomi account password
- `MIIO_COUNTRY` — Cloud region, e.g. `cn`, `de`, `us`, `sg` (default: `de`)
- `MIIO_SENSOR_MODELS` — (optional) comma-separated model name hints to filter thermometers

Without credentials the page renders correctly but shows an error banner. The `python-miio` library authenticates against Xiaomi's cloud service; login may fail if the account has two-factor auth enabled or security restrictions on new device logins. Building `netifaces` (a dependency) requires `python3-dev` and `build-essential` system packages.

### Key Gotchas
1. **`paddleclas` is not in `requirements.txt`** but is required by `detection.py`. Install it separately with `pip install --no-deps paddleclas` followed by `pip install gast easydict ujson visualdl setuptools wheel` to avoid numpy version conflicts with Python 3.12.
2. **`requirements.txt` lists `dotenv`** but the actual PyPI package is `python-dotenv`. Pip resolves this automatically (installs both `dotenv` and `python-dotenv`).
3. **PaddleClas downloads model weights on first inference** (~23 MB for EfficientNetB0). First `/detect` call will be slow.
4. **SQLite DB** (`detect.db`) is auto-created by `database.py` on import — no manual init needed.
5. The `python3.12-venv` system package must be installed (`sudo apt install python3.12-venv`) before creating the venv.
6. **`python3-dev` and `build-essential`** are needed to compile `netifaces` (dependency of `python-miio`).
