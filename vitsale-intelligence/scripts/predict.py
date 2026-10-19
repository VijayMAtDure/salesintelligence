"""
Inference — loads a trained AutoGluon predictor and scores real, current data. Subprocess-
invoked from the Django platform (apps/inference/services/predictor.py), same reuse pattern
as train_forecast.py/train_propensity.py: the proven training/scoring logic stays here, the
web app just orchestrates + tracks it.

PROPENSITY: scores ONE real lead, looked up by source_call_decision_id from
sales_intelligence_feature_snapshot — never a hand-typed feature vector. Reuses
export_training_data.py's PROPENSITY_FEATURES list directly (imported, not copied) so
inference can never silently drift from what the model was actually trained on.

FORECAST: predicts the next `horizon` hours for the single real series (the main
organisation/showroom/UNKNOWN-product series — see PHASE1_DATA_AND_LOGIC_REFERENCE.md item 11
for why product-level series aren't usable), using the same known-future covariates as
training.

Outputs one JSON object to stdout — the caller parses stdout, not a file, since inference is
a single request/response, not a long batch run with its own output directory.
"""
import argparse
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from autogluon.tabular import TabularPredictor
from autogluon.timeseries import TimeSeriesDataFrame, TimeSeriesPredictor

sys.path.insert(0, str(Path(__file__).parent.parent))  # vitasale_intelligence/ itself
from db import SurrealDB, load_config  # noqa: E402
from export_training_data import (  # noqa: E402
    KNOWN_COVARIATES, PROPENSITY_FEATURES, PROPENSITY_FEATURES_META,
    PROPENSITY_FEATURES_REAL_CHANNEL,
)

# label_test_drive_booked_sim, 2026-09-18: the only propensity target trained with the extra
# hyperlocal (Meta) feature columns (see train_propensity.py's LABEL_FEATURE_EXCLUSIONS/target
# choice notes) -- inference must build the same feature set it was trained on, or AutoGluon
# either errors on the missing columns or silently treats them as always-absent, which would
# make meta_to_first_contact_mins useless at inference time even though training picked it up.
TARGET_EXTRA_FEATURES = {
    "label_test_drive_booked_sim": PROPENSITY_FEATURES_META,
}

# config.yaml business_hours: 9am-7pm IST (Asia/Kolkata) -- see train_forecast.py's
# _business_covariates() for the full bug writeup (2026-09-02): bucket_start/timestamp are
# UTC, so recomputing is_business_hours as `timestamp.dt.hour in [9,19)` was checking UTC
# hours against an IST-defined window -- off by 5:30, flagging real business hours as
# "off-hours" and vice versa for the entire future prediction horizon on every inference call.
IST_OFFSET = pd.Timedelta(hours=5, minutes=30)
BUSINESS_START_HOUR, BUSINESS_END_HOUR = 9, 19


def _business_covariates(utc_timestamp: pd.Series) -> tuple:
    ist = utc_timestamp + IST_OFFSET
    hour_of_day = ist.dt.hour
    weekday = ist.dt.weekday
    is_business_hours = (
        (hour_of_day >= BUSINESS_START_HOUR) & (hour_of_day < BUSINESS_END_HOUR)
        & (weekday < 6)
    ).astype(int)
    return hour_of_day, weekday, is_business_hours


def predict_propensity(artifact_path: str, source_call_decision_id: str, target: str) -> dict:
    # Confirmed 2026-09-18 via a real chat tool call: an LLM-supplied id can arrive without the
    # "call_decision:" table prefix (e.g. "zrc8pn0n2prcf2z944a5" instead of
    # "call_decision:zrc8pn0n2prcf2z944a5") even when told the real, prefixed id -- the exact
    # string match below then silently finds nothing. Normalize rather than trust the caller's
    # formatting; source_call_decision_id is always stored WITH the prefix on feature_snapshot.
    if not source_call_decision_id.startswith("call_decision:"):
        source_call_decision_id = f"call_decision:{source_call_decision_id}"

    db = SurrealDB(load_config())
    rows = db.select(
        "SELECT * FROM sales_intelligence_feature_snapshot "
        f"WHERE source_call_decision_id = '{source_call_decision_id}';"
    )
    if not rows:
        return {"error": f"no feature_snapshot found for {source_call_decision_id}"}
    snap = rows[0]

    # ⚠️ FIXED 2026-09-21: is_hyperlocal isn't a real feature_snapshot column -- it's computed
    # at export time (export_training_data.py) by checking lead_id against the REAL
    # sales_intelligence_meta_lead table, same as here. Every currently-trained propensity
    # model now includes it (added to PROPENSITY_FEATURES_REAL_CHANNEL and retrained the same
    # day), so it must be added to every target's feature set here too, unconditionally --
    # unlike TARGET_EXTRA_FEATURES (PROPENSITY_FEATURES_META), which stays label_test_drive_
    # booked_sim-only. snap.get() can't supply it since it was never a stored field.
    is_hyperlocal_rows = db.select(
        f"SELECT id FROM sales_intelligence_meta_lead WHERE lead_id = {snap['lead_id']};"
    )
    is_hyperlocal = 1 if is_hyperlocal_rows else 0

    feature_names = PROPENSITY_FEATURES + PROPENSITY_FEATURES_REAL_CHANNEL + TARGET_EXTRA_FEATURES.get(target, [])
    feature_row = {f: snap.get(f) for f in feature_names}
    feature_row["is_hyperlocal"] = is_hyperlocal
    df = pd.DataFrame([feature_row])

    predictor = TabularPredictor.load(artifact_path, require_version_match=False)
    proba = predictor.predict_proba(df)
    positive_col = proba.columns[-1]  # binary: [negative, positive] — take positive class

    return {
        "track": "PROPENSITY",
        "target": target,
        "source_call_decision_id": source_call_decision_id,
        "lead_id": snap.get("lead_id"),
        "probability": float(proba[positive_col].iloc[0]),
        "model_name": predictor.model_best,
        "features_used": {k: (v if not pd.isna(v) else None) for k, v in feature_row.items()},
    }


def predict_forecast(artifact_path: str, target: str, horizon: int, transform: str = "RAW") -> dict:
    """
    ⚠️ transform BUG FIXED 2026-08-31: this function used to ignore transform entirely,
    always feeding raw values to predictor.predict() and never inverse-transforming the
    output. For a model actually trained with log1p (train_forecast.py --transform LOG1P),
    that means the input the model expects (log-space) never matched what it was given
    (raw-space), and predictions would come back in log-space while being reported as if
    they were real counts — silently wrong by a large factor, not just imprecise. Same fix
    class as train_forecast.py's own log1p bug; caught by the same testing pass.
    """
    use_log1p = transform.upper() == "LOG1P"
    if target.endswith("_sim"):
        # SIMULATED demo variant (2026-08-31): historical context comes from the training
        # CSV, not SurrealDB. The real production sales_intelligence_timeseries table is
        # SCHEMAFULL and deliberately never gets a fabricated column added to it (confirmed:
        # it rejects unknown fields outright) -- so a "_sim" target's synthetic series lives
        # only in its own CSV (see build_sim_test_drive.py), matching what it was trained on.
        # Built as a dense correlated series with no real gaps, so no_campaign stays empty.
        data_dir = Path(__file__).parent.parent / "data"
        df = pd.read_csv(data_dir / f"forecast_{target}.csv")
        df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True).dt.tz_localize(None)
        df["is_business_hours"] = df["is_business_hours"].astype(int)
        df = df.sort_values("timestamp")[["item_id", "timestamp", "target"] + KNOWN_COVARIATES]
        no_campaign = set()
    else:
        db = SurrealDB(load_config())
        rows = db.select("SELECT * FROM sales_intelligence_timeseries;")
        df = pd.DataFrame([r for r in rows if "UNKNOWN" in r["item_id"]])
        df["timestamp"] = pd.to_datetime(df["bucket_start"], utc=True).dt.tz_localize(None)
        # ⚠️ GAP-AWARE FILL PROMOTED TO DEFAULT 2026-09-02 (see train_forecast.py's load()
        # docstring for the validation). Classify no-campaign calendar days from
        # calls_attempted -- the master activity signal, present on every row regardless of
        # which target column we end up using -- and leave those hours as NaN below rather
        # than fabricating a zero.
        daily = df.groupby(df["timestamp"].dt.date)["calls_attempted"].apply(
            lambda s: pd.to_numeric(s, errors="coerce").fillna(0).sum())
        full_range = pd.date_range(daily.index.min(), daily.index.max(), freq="D").date
        no_campaign = {d for d in full_range if daily.get(d, 0) == 0}
        df = df.sort_values("timestamp")[["item_id", "timestamp", target] + KNOWN_COVARIATES]
        df = df.rename(columns={target: "target"})
        df["is_business_hours"] = df["is_business_hours"].astype(int)
    if use_log1p:
        df["target"] = np.log1p(df["target"].astype(float))

    tsdf = TimeSeriesDataFrame.from_data_frame(df, id_column="item_id", timestamp_column="timestamp")
    tsdf = tsdf.convert_frequency(freq="h")
    flat = tsdf.reset_index()
    flat["hour_of_day"], flat["weekday"], flat["is_business_hours"] = \
        _business_covariates(flat["timestamp"])
    flat["active_campaign_count"] = flat["active_campaign_count"].fillna(0)
    is_active_day = ~flat["timestamp"].dt.date.isin(no_campaign)
    flat.loc[is_active_day, "target"] = flat.loc[is_active_day, "target"].fillna(0.0)
    # hours on a genuine no-campaign day stay NaN -- AutoGluon handles this natively, matching
    # how the model was trained (train_forecast.py's load())
    tsdf = TimeSeriesDataFrame.from_data_frame(
        flat, id_column="item_id", timestamp_column="timestamp")

    predictor = TimeSeriesPredictor.load(artifact_path, require_version_match=False)
    future = predictor.make_future_data_frame(tsdf)
    future["timestamp"] = pd.to_datetime(future["timestamp"])
    future["hour_of_day"], future["weekday"], future["is_business_hours"] = \
        _business_covariates(future["timestamp"])
    future["active_campaign_count"] = 0  # not genuinely known-future — see aggregates.py note
    known = TimeSeriesDataFrame.from_data_frame(future, id_column="item_id", timestamp_column="timestamp")

    preds = predictor.predict(tsdf, known_covariates=known).reset_index()
    if use_log1p:
        for c in ("0.1", "0.5", "0.9"):
            if c in preds.columns:
                preds[c] = np.maximum(0, np.expm1(preds[c]))
    points = [
        {
            "timestamp": row["timestamp"].isoformat(),
            "p10": max(0.0, float(row.get("0.1", 0))),
            "p50": max(0.0, float(row.get("0.5", 0))),
            "p90": max(0.0, float(row.get("0.9", 0))),
        }
        for _, row in preds.iterrows()
    ][:horizon]

    # ⚠️ FIXED 2026-09-03: this used to report back the REQUESTED `horizon` verbatim, but the
    # slice above can only ever trim `points`, never extend it -- predictor.predict() always
    # returns exactly the model's trained prediction_length (24 for every model here) regardless
    # of what `--horizon` asked for. A caller requesting e.g. 168 (7 days) silently got 24 hours
    # of real predictions back mislabeled as "horizon_hours": 168 -- confirmed via
    # apps.assistant's get_forecast tool, the first caller to ever pass a horizon other than the
    # UI's fixed 24. Reporting len(points) makes the label honest regardless of what was asked.
    return {
        "track": "FORECAST", "target": target, "horizon_hours": len(points),
        "model_name": predictor.model_best, "predictions": points,
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--track", required=True, choices=["PROPENSITY", "FORECAST"])
    ap.add_argument("--artifact-path", required=True)
    ap.add_argument("--target", help="forecast target name")
    ap.add_argument("--source-call-decision-id", help="propensity: which lead to score")
    ap.add_argument("--horizon", type=int, default=24)
    ap.add_argument("--transform", default="RAW", choices=["RAW", "LOG1P"],
                     help="must match whatever the model at --artifact-path was trained with")
    args = ap.parse_args()

    if args.track == "PROPENSITY":
        if not args.source_call_decision_id:
            print(json.dumps({"error": "--source-call-decision-id required for PROPENSITY"}))
            sys.exit(1)
        result = predict_propensity(args.artifact_path, args.source_call_decision_id, args.target)
    else:
        result = predict_forecast(args.artifact_path, args.target, args.horizon, args.transform)

    print(json.dumps(result))


if __name__ == "__main__":
    main()
