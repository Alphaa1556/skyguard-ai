# SkyGuard AI

AI/ML-based intelligent anomaly detection for Automatic Weather Stations (AWS).

**SIH 2026 — Problem Statement ID: 26073**
Ministry of Earth Sciences (MoES) / India Meteorological Department
Theme: Disaster Management

Team **CodeCrafters**

## Team

| Role | Members |
|---|---|
| Backend | Yash, Bhakti, Ronak |
| Frontend | Shubhaan, Pratik, Arya |
| PPT | Yash, Arya |

## What this is

The system detects abnormal, inconsistent, or faulty observations from AWS units in real time,
using only three parameters: temperature, atmospheric pressure, and relative humidity.

Unlike threshold-based quality control, it:
- Checks multivariate consistency across temp/pressure/humidity together, not one at a time
- Classifies *why* a reading is flagged (spike, flatline, drift, noise, cross-sensor inconsistency)
- Gives a confidence score and an explanation (SHAP), not just a yes/no flag
- Flags degrading sensors before they fail outright

## Project structure

```
skyguard-ai/
├── backend/          FastAPI service — ingestion, ML inference, API endpoints
│   ├── main.py
│   ├── requirements.txt
│   └── data/          synthetic dataset generator + generated data
├── frontend/          React app — dashboard, 3D map, alerts, explainability panel
└── docs/
    └── api-contract.md
```

## Branching model

- `main` — always working, final prototype only
- `test` — integration branch, everyone merges here first
- `feature/<name>` — individual work, branched off `test`

Never push directly to `main`. Open a PR from your `feature/` branch into `test`.
`test` → `main` only when a full working version is ready to demo/submit.

## Getting started

### Backend
```bash
cd backend
pip install -r requirements.txt
uvicorn main:app --reload
```
API will run at `http://localhost:8000`. Interactive docs at `http://localhost:8000/docs`.

### Frontend
```bash
cd frontend
npm create vite@latest . -- --template react
npm install
npm run dev
```

## API contract

See [`docs/api-contract.md`](docs/api-contract.md) — locked before development started, both
teams build against this.
