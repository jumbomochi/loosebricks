import csv
import gzip
import io

import httpx
from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.catalog.models import Color, Moc, MocPart, Part, Set, SetPart

REBRICKABLE_CDN = "https://cdn.rebrickable.com/media/downloads"


class RebrickableSync:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def _download_csv(self, url: str) -> bytes:
        async with httpx.AsyncClient() as client:
            resp = await client.get(url, follow_redirects=True)
            resp.raise_for_status()
            return resp.content

    def _parse_csv(self, data: bytes) -> list[dict]:
        try:
            text_data = gzip.decompress(data).decode("utf-8")
        except gzip.BadGzipFile:
            text_data = data.decode("utf-8")
        reader = csv.DictReader(io.StringIO(text_data))
        return [row for row in reader if any(v for v in row.values())]

    async def sync_catalog(self):
        # Download all CSVs
        parts_data = await self._download_csv(f"{REBRICKABLE_CDN}/parts.csv.gz")
        colors_data = await self._download_csv(f"{REBRICKABLE_CDN}/colors.csv.gz")
        sets_data = await self._download_csv(f"{REBRICKABLE_CDN}/sets.csv.gz")
        inventories_data = await self._download_csv(f"{REBRICKABLE_CDN}/inventories.csv.gz")
        inv_parts_data = await self._download_csv(f"{REBRICKABLE_CDN}/inventory_parts.csv.gz")

        parts_rows = self._parse_csv(parts_data)
        colors_rows = self._parse_csv(colors_data)
        sets_rows = self._parse_csv(sets_data)
        inventories_rows = self._parse_csv(inventories_data)
        inv_parts_rows = self._parse_csv(inv_parts_data)

        # Build inventory_id → set_num mapping (version 1 only)
        inv_to_set = {}
        for row in inventories_rows:
            if row["version"] == "1":
                inv_to_set[row["id"]] = row["set_num"]

        # Clear existing data (respect FK order)
        await self.db.execute(delete(MocPart))
        await self.db.execute(delete(Moc))
        await self.db.execute(delete(SetPart))
        await self.db.execute(delete(Set))
        await self.db.execute(delete(Part))
        await self.db.execute(delete(Color))

        # Insert colors
        for row in colors_rows:
            self.db.add(Color(
                id=int(row["id"]),
                name=row["name"],
                rgb=row["rgb"],
                is_trans=row["is_trans"].lower() in ("t", "true", "1"),
            ))
        await self.db.flush()

        # Insert parts
        for row in parts_rows:
            self.db.add(Part(
                part_num=row["part_num"],
                name=row["name"],
                category_id=int(row["part_cat_id"]),
            ))
        await self.db.flush()

        # Insert sets
        for row in sets_rows:
            self.db.add(Set(
                set_num=row["set_num"],
                name=row["name"],
                year=int(row["year"]),
                num_parts=int(row["num_parts"]),
                theme_id=int(row["theme_id"]),
            ))
        await self.db.flush()

        # Insert set_parts (skip spares)
        for row in inv_parts_rows:
            if row.get("is_spare", "f").lower() in ("t", "true", "1"):
                continue
            set_num = inv_to_set.get(row["inventory_id"])
            if set_num is None:
                continue
            self.db.add(SetPart(
                set_num=set_num,
                part_num=row["part_num"],
                color_id=int(row["color_id"]),
                quantity=int(row["quantity"]),
            ))

        await self.db.commit()
