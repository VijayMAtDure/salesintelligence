#!/usr/bin/env python3
"""STUB — placeholder for the real vitasale_intelligence/server_scripts/train_propensity.py.
See stub_scripts/README.md and train_forecast.py's stub for why this exists.
"""
import argparse
import json
import os
import pathlib


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--label", required=True)
    parser.add_argument("--time-limit", type=int, default=300)
    parser.add_argument("--preset", default="best_quality")
    args = parser.parse_args()

    out_dir = pathlib.Path(os.environ.get("GPU_TRAINING_OUTPUT_DIR", "/tmp/stub_output"))
    out_dir.mkdir(parents=True, exist_ok=True)

    # Path must match job_runner.py's _artifact_path() convention for PROPENSITY jobs.
    models_dir = out_dir.parent / "models" / f"propensity_{args.label}"
    models_dir.mkdir(parents=True, exist_ok=True)
    (models_dir / "STUB_ARTIFACT.txt").write_text(
        "Placeholder artifact - no real model was trained here. See stub_scripts/README.md.\n"
    )

    meta = {
        "best_model": "STUB_MODEL",
        "models_trained": ["STUB_MODEL"],
        "leaderboard": [{"model": "STUB_MODEL", "score_val": 0.5}],
        "test_roc_auc": 0.5,
        "eval_metric": "roc_auc",
        "validation_method": "STUB - no real backtest was run",
        "caveat": "STUB TRAINING RUN - placeholder output, not a real propensity model.",
    }
    meta_path = out_dir / f"propensity_{args.label}_meta.json"
    meta_path.write_text(json.dumps(meta))
    print(json.dumps({"status": "stub-succeeded", "meta_path": str(meta_path)}))


if __name__ == "__main__":
    main()
