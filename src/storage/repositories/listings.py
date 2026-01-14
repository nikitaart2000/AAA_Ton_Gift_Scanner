"""Repository for active listings."""

import logging
from typing import List, Optional
from decimal import Decimal
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from src.core.models import ActiveListing, BLACK_PACK_BACKGROUNDS

logger = logging.getLogger(__name__)


class ListingsRepository:
    """Repository for active_listings table."""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def upsert_listings(self, listings: List[ActiveListing]):
        """Insert or update multiple listings."""
        if not listings:
            return

        query = """
        INSERT INTO active_listings
        (gift_id, gift_name, model, backdrop, pattern, number, price, listed_at, export_at, source, raw_data, last_updated)
        VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, NOW())
        ON CONFLICT (gift_id)
        DO UPDATE SET
            price = EXCLUDED.price,
            gift_name = EXCLUDED.gift_name,
            model = EXCLUDED.model,
            backdrop = EXCLUDED.backdrop,
            pattern = EXCLUDED.pattern,
            number = EXCLUDED.number,
            listed_at = EXCLUDED.listed_at,
            export_at = EXCLUDED.export_at,
            last_updated = NOW()
        """

        for listing in listings:
            try:
                await self.session.execute(
                    text(query),
                    {
                        "1": listing.gift_id,
                        "2": listing.gift_name,
                        "3": listing.model,
                        "4": listing.backdrop,
                        "5": listing.pattern,
                        "6": listing.number,
                        "7": float(listing.price),
                        "8": listing.listed_at,
                        "9": listing.export_at,
                        "10": listing.source.value,
                        "11": listing.raw_data,
                    },
                )
            except Exception as e:
                logger.error(f"Error upserting listing {listing.gift_id}: {e}")

        await self.session.commit()
        logger.debug(f"Upserted {len(listings)} listings")

    async def remove_listing(self, gift_id: str):
        """Remove a listing (when it's bought)."""
        query = "DELETE FROM active_listings WHERE gift_id = $1"
        await self.session.execute(text(query), {"1": gift_id})
        await self.session.commit()
        logger.debug(f"Removed listing {gift_id}")

    async def get_floors(
        self, model: str, backdrop: Optional[str] = None, background_filter: str = "any"
    ) -> dict:
        """Get floor prices for an asset."""
        query = """
        SELECT price
        FROM active_listings
        WHERE model = $1
        """
        params = {"1": model}
        param_count = 1

        if background_filter == "none":
            query += " AND backdrop IS NULL"
        elif background_filter == "black_pack":
            param_count += 1
            query += f" AND backdrop IN ($2, $3)"
            params["2"] = "Black"
            params["3"] = "Black Onyx"
        elif backdrop:
            param_count += 1
            query += f" AND backdrop = ${param_count}"
            params[str(param_count)] = backdrop

        query += " ORDER BY price ASC LIMIT 10"

        result = await self.session.execute(text(query), params)
        rows = result.fetchall()

        prices = [Decimal(str(row[0])) for row in rows]

        return {
            "first": prices[0] if len(prices) > 0 else None,
            "second": prices[1] if len(prices) > 1 else None,
            "third": prices[2] if len(prices) > 2 else None,
            "count": len(prices),
        }

    async def get_listings_for_asset(
        self, model: str, backdrop: Optional[str] = None
    ) -> List[ActiveListing]:
        """Get all listings for an asset."""
        query = """
        SELECT gift_id, gift_name, model, backdrop, pattern, number, price,
               listed_at, export_at, source, raw_data, last_updated
        FROM active_listings
        WHERE model = $1
        """
        params = {"1": model}

        if backdrop:
            query += " AND backdrop = $2"
            params["2"] = backdrop
        elif backdrop == "":
            query += " AND backdrop IS NULL"

        query += " ORDER BY price ASC"

        result = await self.session.execute(text(query), params)
        rows = result.fetchall()

        listings = []
        for row in rows:
            listings.append(
                ActiveListing(
                    gift_id=row[0],
                    gift_name=row[1],
                    model=row[2],
                    backdrop=row[3],
                    pattern=row[4],
                    number=row[5],
                    price=Decimal(str(row[6])),
                    listed_at=row[7],
                    export_at=row[8],
                    source=row[9],
                    raw_data=row[10],
                    last_updated=row[11],
                )
            )

        return listings

    async def count_listings(self, model: str, backdrop: Optional[str] = None) -> int:
        """Count listings for an asset."""
        listings = await self.get_listings_for_asset(model, backdrop)
        return len(listings)
