#!/usr/bin/env python3
"""Upload bulk file locali → Vercel Blob."""

from __future__ import annotations

import argparse
from pathlib import Path

from social_automation.settings import Settings
from social_automation.storage.blob_store import BlobStorage


def main() -> None:
    parser = argparse.ArgumentParser(description="Upload output/ su Vercel Blob")
    parser.add_argument("--source", required=True, type=Path)
    parser.add_argument("--prefix", default="migrated")
    args = parser.parse_args()
    storage = BlobStorage(Settings(storage_backend="vercel_blob"))
    count = 0
    for path in args.source.rglob("*"):
        if not path.is_file():
            continue
        rel = path.relative_to(args.source).as_posix()
        key = f"{args.prefix}/{rel}"
        url = storage.upload(key, path.read_bytes())
        print(f"{rel} -> {url}")
        count += 1
    print(f"Upload completati: {count}")


if __name__ == "__main__":
    main()
