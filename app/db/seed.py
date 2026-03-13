from sqlalchemy import select

from app.db.engine import SessionLocal
from app.db.models import SellerRow
from app.mock.sellers import MOCK_SELLERS


def seed_sellers() -> None:
    db = SessionLocal()
    try:
        existing = db.execute(select(SellerRow)).scalars().first()
        if existing is not None:
            return
        for seller in MOCK_SELLERS:
            db.add(SellerRow(
                id=seller.id,
                name=seller.name,
                status=seller.status.value,
                slack_channel_id=seller.slack_channel_id,
                policies=seller.policies.model_dump(mode="json"),
            ))
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()
