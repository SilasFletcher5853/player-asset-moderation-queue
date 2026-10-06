import asyncio

import httpx

from src.asset_moderator import InfraiImageReviewer, PlayerAsset, QueueName, screen_asset


class ApprovedImage:
    async def approve(self, image: str, event_id: str) -> bool:
        return True


class ReviewImage:
    async def approve(self, image: str, event_id: str) -> bool:
        return False


def test_clean_asset_moves_to_publish_queue():
    asset = PlayerAsset(
        asset_id="banner-17",
        player_id="player-4",
        event_id="upload-202",
        caption="Final round winner",
        image_base64="cGl4ZWxz",
    )

    decision = asyncio.run(screen_asset(asset, ApprovedImage()))

    assert decision.queue is QueueName.PUBLISH
    assert decision.event_type == "asset.screened"
    assert decision.reasons == []


def test_caption_or_image_signal_holds_asset_for_moderation():
    asset = PlayerAsset(
        asset_id="spray-8",
        player_id="player-9",
        event_id="upload-203",
        caption="Stolen account offer",
        image_base64="cGl4ZWxz",
    )

    decision = asyncio.run(screen_asset(asset, ReviewImage()))

    assert decision.queue is QueueName.MODERATION
    assert decision.reasons == ["caption:stolen_account", "image:review_required"]


def test_infrai_receives_base64_as_image_ref():
    def respond(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/v1/image/background_remove"
        assert request.headers["Idempotency-Key"] == "asset-moderation:upload-202"
        assert request.content == b'{"image":{"base64":"cGl4ZWxz"},"format":"png"}'
        return httpx.Response(200, json={"ok": True, "data": {}})

    reviewer = InfraiImageReviewer("test-key", transport=httpx.MockTransport(respond))
    assert asyncio.run(reviewer.approve("cGl4ZWxz", "upload-202"))
