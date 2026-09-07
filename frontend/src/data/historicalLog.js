// There's no historical endpoint in the locked contract (only the current
// reading via GET /stations/{id}/status), so the Historical Explorer builds
// its own log client-side: every time it polls and sees an anomaly, it
// records an entry here. Persisted to localStorage so a page refresh
// doesn't lose everything — useful mid-demo.

const STORAGE_KEY = 'skyguard_anomaly_log_v1'
const MAX_ENTRIES = 500

export function loadLog() {
  try {
    const raw = localStorage.getItem(STORAGE_KEY)
    return raw ? JSON.parse(raw) : []
  } catch {
    return []
  }
}

function saveLog(entries) {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(entries))
  } catch {
    // Storage full or unavailable — fail quietly, the in-memory log still works
    // for the current session.
  }
}

// Adds new anomaly entries, skipping ones already logged (same station +
// timestamp), and trims to the most recent MAX_ENTRIES.
export function appendEntries(existing, newEntries) {
  const seen = new Set(existing.map(e => e.id))
  const additions = newEntries.filter(e => !seen.has(e.id))
  if (!additions.length) return existing
  const merged = [...additions, ...existing]
    .sort((a, b) => new Date(b.timestamp) - new Date(a.timestamp))
    .slice(0, MAX_ENTRIES)
  saveLog(merged)
  return merged
}

export function clearLog() {
  saveLog([])
  return []
}