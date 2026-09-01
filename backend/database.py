"""
database.py — SkyGuard AI
--------------------------
SQLite storage for incoming weather readings, so history survives a
restart and can be queried (needed for Shubhaan's Historical Data
Explorer). Schema matches the POST /ingest contract:

{
  "station_id": "AWS-IND-MH-001",
  "timestamp": "2026-08-29T00:57:23Z",
  "location": { "latitude": 18.9894, "longitude": 73.1175 },
  "readings": { "temperature_c": 28.4, "pressure_hpa": 1008.2, "humidity_pct": 82.5 }
}
"""

import sqlite3

DB_PATH = "weather_data.db"


def init_db(db_path: str = DB_PATH) -> None:
    """Connects to the db file and creates the table if it doesn't exist."""
    conn = sqlite3.connect(db_path)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS readings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            station_id TEXT NOT NULL,
            timestamp TEXT NOT NULL,
            latitude REAL,
            longitude REAL,
            temperature_c REAL,
            pressure_hpa REAL,
            humidity_pct REAL
        )
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_station_time ON readings(station_id, timestamp)")
    conn.commit()
    conn.close()


def insert_reading(data: dict, db_path: str = DB_PATH) -> None:
    """Takes the exact JSON dict from POST /ingest and stores it."""
    location = data.get("location", {})
    readings = data.get("readings", {})
    conn = sqlite3.connect(db_path)
    conn.execute(
        """INSERT INTO readings
           (station_id, timestamp, latitude, longitude, temperature_c, pressure_hpa, humidity_pct)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        (
            data["station_id"],
            data["timestamp"],
            location.get("latitude"),
            location.get("longitude"),
            readings.get("temperature_c"),
            readings.get("pressure_hpa"),
            readings.get("humidity_pct"),
        ),
    )
    conn.commit()
    conn.close()


def get_readings(station_id: str = None, start: str = None, end: str = None,
                  db_path: str = DB_PATH) -> list[dict]:
    """Bonus, for the Historical Data Explorer: filter by station and/or
    a timestamp range (ISO strings, same format as `timestamp` above)."""
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    query = "SELECT * FROM readings WHERE 1=1"
    params = []
    if station_id:
        query += " AND station_id = ?"
        params.append(station_id)
    if start:
        query += " AND timestamp >= ?"
        params.append(start)
    if end:
        query += " AND timestamp <= ?"
        params.append(end)
    query += " ORDER BY timestamp"
    rows = conn.execute(query, params).fetchall()
    conn.close()
    return [dict(r) for r in rows]


if __name__ == "__main__":
    import os
    test_db = "test_weather_data.db"
    if os.path.exists(test_db):
        os.remove(test_db)

    init_db(test_db)

    sample = {
        "station_id": "AWS-IND-MH-001",
        "timestamp": "2026-08-29T00:57:23Z",
        "location": {"latitude": 18.9894, "longitude": 73.1175},
        "readings": {"temperature_c": 28.4, "pressure_hpa": 1008.2, "humidity_pct": 82.5},
    }
    insert_reading(sample, test_db)
    insert_reading({**sample, "timestamp": "2026-08-29T01:02:23Z"}, test_db)

    rows = get_readings(station_id="AWS-IND-MH-001", db_path=test_db)
    print(f"Stored and retrieved {len(rows)} rows:")
    for r in rows:
        print(r)

    os.remove(test_db)
    print("\ninit_db / insert_reading / get_readings all working.")