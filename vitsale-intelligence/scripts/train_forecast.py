#!/usr/bin/env python3
"""STUB — placeholder for the real vitasale_intelligence/server_scripts/train_forecast.py.
See stub_scripts/README.md for why this exists and what it deliberately does not do.
"""
import argparse
import json
import os
import pathlib


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--target", required=True)
    parser.add_argument("--horizon", type=int, default=24)
    parser.add_argument("--time-limit", type=int, default=300)
    parser.add_argument("--preset", default="best_quality")
    parser.add_argument("--transform", default="RAW")
    args = parser.parse_args()

    out_dir = pathlib.Path(os.environ.get("GPU_TRAINING_OUTPUT_DIR", "/tmp/stub_output"))
    out_dir.mkdir(parents=True, exist_ok=True)

    # Path must match job_runner.py's _artifact_path() convention for FORECAST jobs.
    models_dir = out_dir.parent / "models" / f"forecast_{args.target}_{args.horizon}h"
    models_dir.mkdir(parents=True, exist_ok=True)
    (models_dir / "STUB_ARTIFACT.txt").write_text(
        "Placeholder artifact - no real model was trained here. See stub_scripts/README.md.\n"
    )

    meta = {
        "best_model": "STUB_MODEL",
        "models_trained": ["STUB_MODEL"],
        "leaderboard": [{"model": "STUB_MODEL", "score_val": -1.0}],
        "best_score_val": -1.0,
        "eval_metric": "MASE",
        "validation_method": "STUB - no real backtest was run",
        "n_rows": 0,
        "n_series": 1,
        "horizon_hours": args.horizon,
        "caveat": "STUB TRAINING RUN - placeholder output, not a real forecast model.",
    }
    # Filename convention fixed by job_runner.py's _meta_path() - always "24h", regardless
    # of --horizon, since --horizon is always "24" in practice (see job_runner._script_for).
    meta_path = out_dir / f"forecast_{args.target}_24h_meta.json"
    meta_path.write_text(json.dumps(meta))
    print(json.dumps({"status": "stub-succeeded", "meta_path": str(meta_path)}))


if __name__ == "__main__":
    main()
