"""
Read access to sales_intelligence_meta_lead -- the hyperlocal (Meta/Facebook/Instagram Lead
Ads) pre-call metadata table. See hyperlocal/HYPERLOCAL_META_LEAD_INTEGRATION.md for the full
field spec and where each field comes from.
"""
from apps.datastore.surreal_client import get_client


def channel_fields_by_lead_id() -> dict[str, dict]:
    """{lead_id (str): {platform, is_organic, campaign_name}} -- channel/campaign attribution
    for hyperlocal cross-tabs. ad_id/ad_name/adset fields exist on the table too but aren't
    exposed as query dimensions yet -- add them here if/when a real paid-ad campaign makes
    that worth asking about (today's only real example is organic, so these are mostly empty)."""
    db = get_client()
    rows = db.select(
        "SELECT lead_id, platform, is_organic, campaign_name FROM sales_intelligence_meta_lead;"
    )
    return {
        str(r["lead_id"]): {
            "platform": r.get("platform"),
            "is_organic": r.get("is_organic"),
            "campaign_name": r.get("campaign_name") or None,  # "" and NONE both mean "no campaign"
        }
        for r in rows
    }
