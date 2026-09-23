"""
Read access to master_product_price_list — the vehicle catalog (XC60/XC90/EC40/EX30 in this
pilot). Small, rarely-changing reference table; no filters needed.
"""
from apps.datastore.surreal_client import get_client


def model_by_product_id() -> dict[str, str]:
    """{product_id (str): model name} — for turning feature_snapshot.product_id (a record
    link) back into a human-readable model name when grouping/reporting by product."""
    db = get_client()
    rows = db.select("SELECT id, model FROM master_product_price_list;")
    return {str(r["id"]): r.get("model") for r in rows}
