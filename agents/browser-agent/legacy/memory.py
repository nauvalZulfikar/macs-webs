"""SQLite-backed session memory for the browser agent."""
import json
import sqlite3
import time
from pathlib import Path
from typing import Any


SCHEMA = """
CREATE TABLE IF NOT EXISTS runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    started_at REAL NOT NULL,
    ended_at REAL,
    task TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'running',
    final_answer TEXT
);
CREATE TABLE IF NOT EXISTS steps (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id INTEGER NOT NULL,
    idx INTEGER NOT NULL,
    ts REAL NOT NULL,
    url TEXT,
    action TEXT NOT NULL,
    args_json TEXT,
    obs_json TEXT,
    model TEXT,
    FOREIGN KEY(run_id) REFERENCES runs(id)
);
CREATE TABLE IF NOT EXISTS facts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    domain TEXT NOT NULL,
    key TEXT NOT NULL,
    value TEXT NOT NULL,
    updated_at REAL NOT NULL,
    UNIQUE(domain, key)
);
"""


class Memory:
    def __init__(self, db_path: str):
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(db_path)
        self.conn.executescript(SCHEMA)
        self.conn.commit()

    def start_run(self, task: str) -> int:
        cur = self.conn.execute(
            "INSERT INTO runs(started_at, task) VALUES (?, ?)",
            (time.time(), task),
        )
        self.conn.commit()
        return cur.lastrowid

    def end_run(self, run_id: int, status: str, final_answer: str | None = None):
        self.conn.execute(
            "UPDATE runs SET ended_at=?, status=?, final_answer=? WHERE id=?",
            (time.time(), status, final_answer, run_id),
        )
        self.conn.commit()

    def log_step(
        self,
        run_id: int,
        idx: int,
        url: str | None,
        action: str,
        args: dict[str, Any] | None,
        obs: dict[str, Any] | None,
        model: str | None,
    ):
        self.conn.execute(
            "INSERT INTO steps(run_id, idx, ts, url, action, args_json, obs_json, model) VALUES (?,?,?,?,?,?,?,?)",
            (
                run_id,
                idx,
                time.time(),
                url,
                action,
                json.dumps(args) if args else None,
                json.dumps(obs) if obs else None,
                model,
            ),
        )
        self.conn.commit()

    def remember(self, domain: str, key: str, value: str):
        self.conn.execute(
            "INSERT INTO facts(domain,key,value,updated_at) VALUES (?,?,?,?) "
            "ON CONFLICT(domain,key) DO UPDATE SET value=excluded.value, updated_at=excluded.updated_at",
            (domain, key, value, time.time()),
        )
        self.conn.commit()

    def recall(self, domain: str) -> dict[str, str]:
        rows = self.conn.execute(
            "SELECT key, value FROM facts WHERE domain=?", (domain,)
        ).fetchall()
        return {k: v for k, v in rows}

    def close(self):
        self.conn.close()
