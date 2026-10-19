#!/usr/bin/env python3
"""STUB — placeholder for the real vitasale_intelligence/run_features.py. Does nothing and
exits 0. See backfill.py's stub and stub_scripts/README.md for why this exists.
"""
import argparse

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", required=True)
    parser.add_argument("--feature-version", default=None)
    args = parser.parse_args()
    print(f"stub run_features --mode {args.mode}: no-op")
