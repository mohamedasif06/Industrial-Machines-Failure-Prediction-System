# Industrial Machine Failure Forecasting — frontend

React, TypeScript, Vite, and locally compiled Tailwind frontend for the project. The four existing views keep their design and consume the Phase 6 FastAPI REST and WebSocket interfaces. No inference or Type preprocessing is duplicated in the browser.

## Run both services in Windows PowerShell

Use two PowerShell terminals from the project root.

**Terminal 1 — backend**

```powershell
Set-Location .\backend
..\.venv\Scripts\python.exe -m app
```

The backend defaults to `http://127.0.0.1:8000`. Its interactive API documentation is at `http://127.0.0.1:8000/docs`.

**Terminal 2 — frontend**

```powershell
Set-Location .\frontend
npm install
npm run dev
```

Open the Vite URL printed in the terminal (default `http://127.0.0.1:5173`). Stop each service with Ctrl+C in its terminal. Backend CORS allows both `http://127.0.0.1:5173` and `http://localhost:5173` by default.

Open the app at the Vite URL and choose **Create an account** to register. Successful registration signs the user in and opens Operations Overview. Existing users choose **Sign in**. Sign out is available in the dashboard shell. If the backend cannot be reached, check its CORS setting, database path, and that the backend was started before retrying.

## Frontend configuration

Vite uses `VITE_API_BASE_URL` for REST and derives `ws:` or `wss:` `/ws/telemetry` from that URL. The local default is `http://127.0.0.1:8000`. `VITE_STALE_AFTER_MS` sets the no-valid-update threshold in milliseconds (default `60000`). To override, create `frontend/.env.local` using `.env.example` as a template, then restart Vite. These settings contain no secrets.

## Data source and status

The app loads current latest-per-machine state from `GET /api/machines`, event history from `GET /api/events?limit=500`, and simulator state from `GET /api/simulator/status`. It then subscribes to `WS /ws/telemetry`. Incoming and initial events are validated against the six agreed features and deduplicated by machine ID plus timestamp before being added to the shared event history. Machine counts use each machine's newest event; event counts count individual unique records.

The top bar provides controls for **Normal**, **Mixed**, and **Fault scenario** runs, a configurable machine count, and stop. Mixed runs assign normal and fault-scenario sensor generation to alternating stable machine IDs by default; the backend also accepts an explicit `machine_modes` list. Every event still uses the saved model inference function, so mixed mode does not guarantee any class-1 predictions. Events from the backend simulator are labeled **SIMULATED DATA**. There is no automatic fallback to the old fixed demo fixture: backend errors are shown with a retry action. The previous `public/demo-events.jsonl` remains on disk for provenance but is not loaded by the application.

Connected is shown only after the browser's WebSocket `open` event. A lost connection changes to Reconnecting while retries run; Disconnected is shown before a connection is established. Last successful REST/event update time is shown separately from socket status. Machine readings and the overall feed become stale according to the configured threshold. Backend history is in memory and resets on backend restart.

The navigation alert badge shows active backend-managed alert episodes, not the number of class 1 telemetry events. The Alerts page lists active and resolved episodes separately. By default the backend requires two consecutive class 1 predictions to activate an alert and three consecutive class 0 predictions to resolve it. Confirmation reduces transient noise but can delay alert creation. Thresholds and retained alert history are configurable on the backend; reconnecting clients reload the current alert snapshot from `GET /api/alerts`.

All simulator readings are synthetic. A predicted class is a model output, not a confirmed physical breakdown; the estimated probability is not a guarantee, and no exact failure time is predicted. The model uses the existing saved inference, mapping, model artifacts, and exactly these six inputs: `Type`, `Air temperature [K]`, `Process temperature [K]`, `Rotational speed [rpm]`, `Torque [Nm]`, and `Tool wear [min]`.

## Checks

From the frontend directory:

```powershell
npm run lint
npm test
npm run build
```

From the project root, run backend plus existing simulator regression tests:

```powershell
.\.venv\Scripts\python.exe -m pytest -p no:cacheprovider .\backend\tests .\tests\test_simulator.py -q
```
