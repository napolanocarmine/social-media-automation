#!/usr/bin/env python3
"""Migrazione dati SQLite → Postgres (one-shot)."""

from __future__ import annotations

import argparse
import json
import sqlite3
from pathlib import Path

import psycopg
from psycopg.rows import dict_row


def main() -> None:
    parser = argparse.ArgumentParser(description="Migra SQLite verso Postgres")
    parser.add_argument("--sqlite", required=True, type=Path)
    parser.add_argument("--postgres", required=True, help="DATABASE_URL_UNPOOLED")
    args = parser.parse_args()

    src = sqlite3.connect(args.sqlite)
    src.row_factory = sqlite3.Row

    with psycopg.connect(args.postgres, row_factory=dict_row) as dst:
        for table in ("images", "metadata", "planning_events", "batches", "batch_items"):
            rows = src.execute(f"SELECT * FROM {table}").fetchall()
            print(f"{table}: {len(rows)} righe")
            # Migrazione semplificata — estendere per produzione con mapping colonne
        dst.commit()
    print("Migrazione completata (stub — estendere per dati produzione)")


if __name__ == "__main__":
    main()
