import pytest
from unittest.mock import patch

from app.catalog.sync import RebrickableSync


def make_csv(header: str, rows: list[str]) -> bytes:
    content = header + "\n" + "\n".join(rows) + "\n"
    return content.encode("utf-8")


class TestRebrickableSync:
    @pytest.mark.asyncio
    async def test_sync_parts(self, db_session):
        csv_data = {
            "parts.csv.gz": make_csv("part_num,name,part_cat_id", ["3001,Brick 2x4,1", "3003,Brick 2x2,1"]),
            "colors.csv.gz": make_csv("id,name,rgb,is_trans", ["1,Red,FF0000,f", "4,Blue,0000FF,f"]),
            "sets.csv.gz": make_csv("set_num,name,year,theme_id,num_parts", ["10281-1,Bonsai Tree,2021,252,878"]),
            "inventories.csv.gz": make_csv("id,version,set_num", ["1,1,10281-1"]),
            "inventory_parts.csv.gz": make_csv(
                "inventory_id,part_num,color_id,quantity,is_spare",
                ["1,3001,1,10,f", "1,3003,4,5,f", "1,3001,4,2,t"],
            ),
        }

        async def fake_download(url: str) -> bytes:
            for name, data in csv_data.items():
                if url.endswith("/" + name):
                    return data
            raise ValueError(f"Unexpected URL: {url}")

        syncer = RebrickableSync(db_session)
        with patch.object(syncer, "_download_csv", side_effect=fake_download):
            await syncer.sync_catalog()

        from sqlalchemy import select, func
        from app.catalog.models import Part, Color, Set, SetPart

        parts = (await db_session.execute(select(func.count()).select_from(Part))).scalar()
        assert parts == 2

        colors = (await db_session.execute(select(func.count()).select_from(Color))).scalar()
        assert colors == 2

        sets = (await db_session.execute(select(func.count()).select_from(Set))).scalar()
        assert sets == 1

        # Only non-spare parts (2 rows, not 3)
        set_parts = (await db_session.execute(select(func.count()).select_from(SetPart))).scalar()
        assert set_parts == 2

    @pytest.mark.asyncio
    async def test_sync_is_idempotent(self, db_session):
        csv_data = {
            "parts.csv.gz": make_csv("part_num,name,part_cat_id", ["3001,Brick 2x4,1"]),
            "colors.csv.gz": make_csv("id,name,rgb,is_trans", ["1,Red,FF0000,f"]),
            "sets.csv.gz": make_csv("set_num,name,year,theme_id,num_parts", []),
            "inventories.csv.gz": make_csv("id,version,set_num", []),
            "inventory_parts.csv.gz": make_csv("inventory_id,part_num,color_id,quantity,is_spare", []),
        }

        async def fake_download(url: str) -> bytes:
            for name, data in csv_data.items():
                if url.endswith("/" + name):
                    return data
            raise ValueError(f"Unexpected URL: {url}")

        syncer = RebrickableSync(db_session)
        with patch.object(syncer, "_download_csv", side_effect=fake_download):
            await syncer.sync_catalog()
            await syncer.sync_catalog()  # Run again

        from sqlalchemy import select, func
        from app.catalog.models import Part

        parts = (await db_session.execute(select(func.count()).select_from(Part))).scalar()
        assert parts == 1
