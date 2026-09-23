"""
Read access to `lead` -- the real, externally-owned MDB table (not one of ours). Deliberately
minimal: only what's needed for lead-level cross-tab analysis, never the full ~30-field row.
"""
from apps.datastore.surreal_client import get_client

FREE_EMAIL_DOMAINS = {
    "gmail.com", "yahoo.com", "yahoo.co.in", "hotmail.com", "outlook.com",
    "icloud.com", "rediffmail.com", "live.com", "aol.com", "protonmail.com",
}


def email_domain_type(email: str | None) -> str | None:
    """'personal' (free webmail) vs 'business' (any other domain) -- a plausible fleet/
    corporate-buyer signal, distinct from a retail one. None if there's no email at all."""
    if not email or "@" not in email:
        return None
    domain = email.rsplit("@", 1)[-1].strip().lower()
    return "personal" if domain in FREE_EMAIL_DOMAINS else "business"


def city_and_email_by_id() -> dict[str, dict]:
    """{lead_id (str): {city, email_domain_type}} -- for joining hyperlocal cross-tabs against
    location and personal-vs-business-email, both of which live on `lead` itself, not on
    sales_intelligence_meta_lead (no need to duplicate fields lead already has)."""
    db = get_client()
    rows = db.select("SELECT id, city, email FROM lead;")
    return {
        str(r["id"]): {
            "city": r.get("city"),
            "email_domain_type": email_domain_type(r.get("email")),
        }
        for r in rows
    }
