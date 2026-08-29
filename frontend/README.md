# SkyGuard AI — Frontend

Team CodeCrafters · PS 26073 · Day 1 scaffold

## Run it

```bash
npm install
npm run dev
```

Opens at `http://localhost:5173`.

## What's here

- **Hero** (`src/components/Hero.jsx`) — the opening moment: a radar sweep with
  live station blips and a waveform that periodically morphs from clean into
  an anomalous spike, dramatizing "detect → explain" before the user scrolls.
- **Dashboard** (`src/components/Dashboard.jsx`) — station list, per-station
  temperature/pressure/humidity line charts (Recharts), an explainability
  panel (type + confidence bar + plain-language reason), and a live alert
  center. Polls every 8s to simulate `GET /stations/{id}/status`.
- **Mock data** (`src/data/mockStations.js`) — shaped exactly to the locked
  contract (`readings`, `anomaly.type/confidence/explanation/affected_parameter`,
  `sensor_health`). `fetchStations()` / `fetchStationStatus()` are the two
  functions to swap for real `fetch()` calls once backend is up — nothing
  else in the components needs to change.

## Design tokens

Defined in `src/index.css` — deep-navy "ops room" background, teal for
nominal readings, amber for degraded/drift, red for confirmed anomalies.
Fonts: Space Grotesk (display), Inter (body), JetBrains Mono (data/labels).

## Next (per the workflow doc)

- Day 2-3: wire Live Anomaly Alert Center refinements (Arya)
- Day 1-4: swap the hero's flat station field for the react-three-fiber 3D
  globe (Pratik) — `Hero.jsx`'s `STATION_DOTS` array is a good reference for
  station coordinates until then
- Day 7-8: point `mockStations.js`'s two fetch functions at the real
  `/stations` and `/stations/{id}/status` endpoints
- Day 6-7: Historical Data Explorer (Shubhaan)

## Branch

Work on `feature/dashboard`, PR into `test` — see the team's git workflow doc.
