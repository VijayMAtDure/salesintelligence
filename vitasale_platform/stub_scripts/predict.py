#!/usr/bin/env python3
"""STUB — placeholder for the real vitasale_intelligence/server_scripts/predict.py.
Returns a clearly-fabricated result so apps.inference.services.predictor's Django-side job
handling (result storage, narrative generation) can be exercised for real. The LAST line of
stdout must be exactly one JSON object — apps.inference.services.predictor.run_inference()
parses only that line.
"""
import argparse
import json


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--track", required=True)
    parser.add_argument("--artifact-path", required=True)
    parser.add_argument("--target", required=True)
    parser.add_argument("--horizon", type=int, default=24)
    parser.add_argument("--transform", default="RAW")
    parser.add_argument("--source-call-decision-id", default=None)
    args = parser.parse_args()

    if args.track == "PROPENSITY":
        result = {
            "track": "PROPENSITY",
            "target": args.target,
            "source_call_decision_id": args.source_call_decision_id,
            "prediction": 0.5,
            "provenance": "SIMULATED",
            "caveat": "STUB PREDICTION - placeholder output, not a real propensity score.",
        }
    else:
        result = {
            "track": "FORECAST",
            "target": args.target,
            "horizon_hours": args.horizon,
            "transform": args.transform,
            "values": [0] * args.horizon,
            "provenance": "SIMULATED",
            "caveat": "STUB PREDICTION - placeholder output, not a real forecast.",
        }
    print(json.dumps(result))


if __name__ == "__main__":
    main()
