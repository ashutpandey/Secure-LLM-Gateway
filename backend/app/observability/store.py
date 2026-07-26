"""Durable audit store — makes the tamper-evident audit survive restarts.

Backed by stdlib sqlite3 (no new dependency). Audit writes are on the SYNCHRONOUS
path by design (Cycle 5), and inserts are tiny, so a sync sqlite write fits. On
startup the AuditSink loads the last hash + seq so the hash chain CONTINUES across
restarts rather than resetting — real durable, verifiable history.

A full async SQLAlchemy/Postgres store is the scale-out upgrade; this same
interface (append / recent / last) is what it would implement.
"""

from __future__ import annotations

import sqlite3
from typing import Protocol

_GENESIS = "0" * 64


class AuditStore(Protocol):
    def append(self, entry: dict) -> None: ...
    def recent(self, n: int) -> list[dict]: ...
    def last(self) -> tuple[int, str]: ...  # (last_seq, last_hash)


class SqliteAuditStore:
    def __init__(self, path: str) -> None:
        # `check` is a SQL keyword -> store it as check_ and remap on read.
        self._conn = sqlite3.connect(path, check_same_thread=False)
        self._conn.execute(
            """
            CREATE TABLE IF NOT EXISTS audit (
                seq INTEGER PRIMARY KEY,
                kind TEXT, conversation_id TEXT, action TEXT,
                check_ TEXT, provider TEXT, prev TEXT, hash TEXT
            )
            """
        )
        self._conn.commit()

    def append(self, e: dict) -> None:
        self._conn.execute(
            "INSERT OR REPLACE INTO audit VALUES (?,?,?,?,?,?,?,?)",
            (e["seq"], e["kind"], e["conversation_id"], e["action"], e["check"], e["provider"], e["prev"], e["hash"]),
        )
        self._conn.commit()

    def recent(self, n: int) -> list[dict]:
        cur = self._conn.execute(
            "SELECT seq,kind,conversation_id,action,check_,provider,prev,hash "
            "FROM audit ORDER BY seq DESC LIMIT ?",
            (n,),
        )
        rows = cur.fetchall()
        rows.reverse()
        return [
            {
                "seq": r[0], "kind": r[1], "conversation_id": r[2], "action": r[3],
                "check": r[4], "provider": r[5], "prev": r[6], "hash": r[7],
            }
            for r in rows
        ]

    def last(self) -> tuple[int, str]:
        cur = self._conn.execute("SELECT seq,hash FROM audit ORDER BY seq DESC LIMIT 1")
        r = cur.fetchone()
        return (r[0], r[1]) if r else (0, _GENESIS)
