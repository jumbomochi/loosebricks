from dataclasses import dataclass
from typing import Protocol

import httpx

from app.config import settings


@dataclass
class Prediction:
    part_num: str
    color_id: int
    confidence: float
    bbox: dict | None


class MLClient(Protocol):
    async def predict(self, image_url: str, request_id: str) -> list[Prediction]:
        ...


class BrickognizeAdapter:
    def __init__(self):
        self._http_client = httpx.AsyncClient(
            base_url=settings.brickognize_api_url,
            timeout=30.0,
        )

    async def predict(self, image_url: str, request_id: str) -> list[Prediction]:
        async with httpx.AsyncClient() as download_client:
            img_resp = await download_client.get(image_url)
            img_resp.raise_for_status()

        response = await self._http_client.post(
            "/predict/",
            files={"image": ("photo.jpg", img_resp.content, "image/jpeg")},
        )
        response.raise_for_status()
        data = response.json()

        predictions = []
        for item in data.get("items", []):
            bbox = None
            if "bounding_box" in item:
                bb = item["bounding_box"]
                bbox = {"x": bb["x"], "y": bb["y"], "w": bb["width"], "h": bb["height"]}

            predictions.append(Prediction(
                part_num=item["id"],
                color_id=item["color"]["id"],
                confidence=item["score"],
                bbox=bbox,
            ))

        return predictions
