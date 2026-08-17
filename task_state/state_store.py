"""Phase 17: durable task state via SQLite. No external DB server."""
import json
import sqlite3
import time
from pathlib import Path

DB_PATH = Path(r"C:\AI\control-plane\task_state\state.db")

SCHEMA = """
CREATE TABLE IF NOT EXISTS tasks (
    task_id TEXT PRIMARY KEY,
    project_id TEXT,
    created_at REAL,
    updated_at REAL,
    objective TEXT,
    classification TEXT,
    required_capability TEXT,
    agent TEXT,
    model TEXT,
    provider TEXT,
    plan TEXT,
    completed_steps TEXT,
    active_step TEXT,
    modified_files TEXT,
    fallback_history TEXT,
    status TEXT
);
"""

VALID_STATUSES = {
    "CREATED", "PLANNING", "EXECUTING", "WAITING", "FALLING_BACK",
    "VERIFYING", "FAILED", "BLOCKED", "COMPLETED", "CANCELLED",
}

def _conn():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH, timeout=10)
    # WAL mode: default 'delete' journal mode serializes ALL writers with a
    # single file lock - a real problem once Claude + OpenCode Go + Codex can
    # all be dispatching (and updating task state) concurrently. WAL lets
    # readers and a writer coexist and reduces 'database is locked' failures.
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute(SCHEMA)
    return conn

def create_task(task_id: str, objective: str, project_id: str = None) -> None:
    now = time.time()
    with _conn() as c:
        c.execute(
            "INSERT OR REPLACE INTO tasks (task_id, project_id, created_at, updated_at, "
            "objective, status, completed_steps, fallback_history) VALUES (?,?,?,?,?,?,?,?)",
            (task_id, project_id, now, now, objective, "CREATED", "[]", "[]"),
        )

def update_task(task_id: str, **fields) -> None:
    if "status" in fields and fields["status"] not in VALID_STATUSES:
        raise ValueError(f"invalid status {fields['status']}")
    fields["updated_at"] = time.time()
    for k in ("plan", "completed_steps", "modified_files", "fallback_history"):
        if k in fields and not isinstance(fields[k], str):
            fields[k] = json.dumps(fields[k])
    cols = ", ".join(f"{k}=?" for k in fields)
    with _conn() as c:
        c.execute(f"UPDATE tasks SET {cols} WHERE task_id=?", (*fields.values(), task_id))

def get_task(task_id: str) -> dict | None:
    with _conn() as c:
        row = c.execute("SELECT * FROM tasks WHERE task_id=?", (task_id,)).fetchone()
        if not row:
            return None
        cols = [d[0] for d in c.execute("SELECT * FROM tasks LIMIT 0").description]
        return dict(zip(cols, row))

def list_tasks(limit: int = 20, provider: str | None = None, status: str | None = None) -> list:
    """Real tracking gap closed 2026-08-15: task_state had per-task lookup
    but no way to see history across a session or across all three legs.
    Ordered most-recent-first."""
    with _conn() as c:
        cols = [d[0] for d in c.execute("SELECT * FROM tasks LIMIT 0").description]
        q = "SELECT * FROM tasks"
        clauses, params = [], []
        if provider:
            clauses.append("provider=?"); params.append(provider)
        if status:
            clauses.append("status=?"); params.append(status)
        if clauses:
            q += " WHERE " + " AND ".join(clauses)
        q += " ORDER BY updated_at DESC LIMIT ?"
        params.append(limit)
        rows = c.execute(q, params).fetchall()
        return [dict(zip(cols, r)) for r in rows]

if __name__ == "__main__":
    create_task("smoke-test-1", "verify state store works")
    update_task("smoke-test-1", status="COMPLETED", completed_steps=["init"])
    print(get_task("smoke-test-1"))
