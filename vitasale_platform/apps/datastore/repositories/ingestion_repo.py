"""Read access for previewing what a CSV upload actually inserted — matches rows by the
_csv_upload_id tag csv_loader.py writes onto every row it inserts."""
from apps.datastore.surreal_client import get_client


def sample_uploaded_rows(target_table: str, upload_id: str, limit: int = 20) -> list[dict]:
    db = get_client()
    return db.select(
        f"SELECT * FROM {target_table} WHERE _csv_upload_id = '{upload_id}' LIMIT {int(limit)};"
    )
