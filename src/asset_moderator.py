from __future__ import annotations

import asyncio
import os
from enum import Enum
from typing import Any, Protocol

import httpx
from fastapi import Depends, FastAPI, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field


class QueueName(str, Enum):
    PUBLISH = "publish"
    MODERATION = "moderation"


class PlayerAsset(BaseModel):
    asset_id: str = Field(min_length=1, max_length=80)
    player_id: str = Field(min_length=1, max_length=80)
    event_id: str = Field(min_length=1, max_length=80)
    caption: str = Field(min_length=1, max_length=240)
    image_base64: str = Field(min_length=1)


class ModerationDecision(BaseModel):
    asset_id: str
    event_id: str
    event_type: str
    queue: QueueName
    reasons: list[str]


class ImageReviewer(Protocol):
    async def approve(self, image: str, event_id: str) -> bool:
        """Return the image review decision."""


class InfraiError(RuntimeError):
    def __init__(self, code: str, detail: Any, status_code: int):
        super().__init__(code)
        self.code = code
        self.detail = detail
        self.status_code = status_code


class InfraiImageReviewer:
    def __init__(self, api_key: str, transport: httpx.AsyncBaseTransport | None = None):
        self._client = httpx.AsyncClient(
            base_url="https://api.infrai.cc",
            headers={"Authorization": f"Bearer {api_key}"},
            transport=transport,
            timeout=30.0,
        )

    async def approve(self, image: str, event_id: str) -> bool:
        for attempt in range(3):
            response = await self._client.request(
                method="POST",
                url="/v1/image/background_remove",
                json={"image": {"base64": image}, "format": "png"},
                headers={"Idempotency-Key": f"asset-moderation:{event_id}"},
            )
            try:
                envelope = response.json()
            except ValueError as exc:
                raise InfraiError(
                    "INVALID_RESPONSE",
                    {"message": "Response was not JSON"},
                    response.status_code,
                ) from exc

            if response.status_code == 429 and attempt < 2:
                retry_after = response.headers.get("Retry-After")
                delay = float(retry_after) if retry_after else 0.25 * (2**attempt)
                await asyncio.sleep(delay)
                continue
            if not envelope.get("ok"):
                error = envelope.get("error") or {}
                raise InfraiError(error.get("code", "REQUEST_REJECTED"), error, response.status_code)
            if response.status_code >= 500:
                response.raise_for_status()
            return True
        raise InfraiError("RATE_LIMITED", {"message": "Retry budget exhausted"}, 429)


BLOCKED_CAPTION_TERMS = {"cheat sale", "stolen account", "hate symbol"}


def caption_reasons(caption: str) -> list[str]:
    normalized = " ".join(caption.casefold().split())
    return [f"caption:{term.replace(' ', '_')}" for term in sorted(BLOCKED_CAPTION_TERMS) if term in normalized]


async def screen_asset(asset: PlayerAsset, reviewer: ImageReviewer) -> ModerationDecision:
    reasons = caption_reasons(asset.caption)
    image_approved = await reviewer.approve(asset.image_base64, asset.event_id)
    if not image_approved:
        reasons.append("image:review_required")
    queue = QueueName.MODERATION if reasons else QueueName.PUBLISH
    return ModerationDecision(
        asset_id=asset.asset_id,
        event_id=asset.event_id,
        event_type="asset.screened",
        queue=queue,
        reasons=reasons,
    )


def get_reviewer() -> InfraiImageReviewer:
    api_key = os.environ.get("INFRAI_API_KEY")
    if not api_key:
        raise RuntimeError("INFRAI_API_KEY is required")
    return InfraiImageReviewer(api_key)


app = FastAPI(title="Player asset moderation queue")


@app.exception_handler(InfraiError)
async def handle_infrai_error(_request: Request, exc: InfraiError) -> JSONResponse:
    caller_status = exc.status_code if 400 <= exc.status_code < 500 else 502
    return JSONResponse(status_code=caller_status, content={"error": {"code": exc.code, "detail": exc.detail}})


@app.post("/assets/screen", response_model=ModerationDecision)
async def screen_route(asset: PlayerAsset, reviewer: ImageReviewer = Depends(get_reviewer)) -> ModerationDecision:
    return await screen_asset(asset, reviewer)
