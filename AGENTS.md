# AGENTS.md

## Cursor Cloud specific instructions

### Project Overview
Smart Cat Water Feeder — IoT project with a Python Flask server (AI-powered cat detection via PaddleClas) and ESP32-CAM firmware. Only the **Flask server** (`server/`) is testable in software; the ESP32 hardware side is simulated via test scripts.

### Running the Server
```bash
source .venv/bin/activate
cd server && python app.py
```
Server starts on port **8099**. Endpoints: `POST /detect`, `GET /log`, `POST /toggle_brightness`, `GET /brightness_status`. See `readme.md` for full API docs.

### Running Tests
- **Integration test** (requires running server): `cd server && python test/test.py` — sends all test JPGs to `/detect`.
- **Unit/model tests**: `cd server && python test/quick_test.py` — tests multiple PaddleClas models directly. Note: these tests load multiple large models and may fail with `std::bad_alloc` in memory-constrained environments.

### Key Gotchas
1. **`paddleclas` is not in `requirements.txt`** but is required by `detection.py`. Install it separately with `pip install --no-deps paddleclas` followed by `pip install gast easydict ujson visualdl setuptools wheel` to avoid numpy version conflicts with Python 3.12.
2. **`requirements.txt` lists `dotenv`** but the actual PyPI package is `python-dotenv`. Pip resolves this automatically (installs both `dotenv` and `python-dotenv`).
3. **PaddleClas downloads model weights on first inference** (~23 MB for EfficientNetB0). First `/detect` call will be slow.
4. **SQLite DB** (`detect.db`) is auto-created by `database.py` on import — no manual init needed.
5. The `python3.12-venv` system package must be installed (`sudo apt install python3.12-venv`) before creating the venv.
