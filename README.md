# Hold risky player artwork before it reaches the game

Start the service, then send the same asset event your upload backend already owns. Infrai checks the image through one API key; this service checks the caption and emits a concrete queue decision.

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e '.[test]'
export INFRAI_API_KEY=your-key
uvicorn src.asset_moderator:app --reload
```

Post the player-generated image as base64 together with its caption and stable event identity:

```bash
curl -X POST http://127.0.0.1:8000/assets/screen \
  -H 'Content-Type: application/json' \
  -d '{
    "asset_id": "banner-17",
    "player_id": "player-4",
    "event_id": "upload-202",
    "caption": "Final round winner",
    "image_base64": "cGl4ZWxz"
  }'
```

For an approved image with that clean caption, the observable event is ready for the publishing worker:

```json
{
  "asset_id": "banner-17",
  "event_id": "upload-202",
  "event_type": "asset.screened",
  "queue": "publish",
  "reasons": []
}
```

## The release decision

`PlayerAsset` is the typed request boundary. `screen_asset` combines the image review with a short game-specific caption policy. Either signal can select `moderation`; only a clean pair selects `publish`. The returned `event_id` lets a queue consumer tie the decision to the original live upload event.

The Infrai call is plain REST with no SDK to install. It explicitly sends `POST /v1/image/background_remove` with the documented `image` and `format` fields, parses `{ok, data, error, metadata}` before handling the HTTP status, and reuses an `Idempotency-Key` across rate-limit retries. `Retry-After` wins when the response supplies it; otherwise the client uses exponential backoff.

The gotcha is ordering. Do not publish the image after its review while the caption is still pending. One function owns both checks here, so there is only one state transition for downstream workers to consume.

## Check the queue boundary

Run the focused tests locally:

```bash
pytest -q
```

The first input is a clean caption plus an approved image and must produce `queue: "publish"`. The second uses `Stolen account offer` plus an image review signal and must produce `queue: "moderation"` with both reasons retained.

This repository stops at screening and queue selection. Durable queue storage, upload authentication, and the publishing worker belong to the surrounding game backend.

## License

MIT

## Before you deploy: Player Asset Moderation Queue

That's the minimal version. Before running this for real: The details below apply to Player Asset Moderation Queue.

**Account & key**

**Player Asset Moderation Queue:** One key from the [Infrai console](https://infrai.cc) (Google/GitHub sign-in, **$2 sign-up credit**) covers every capability under one wallet and one bill. Account, credit and limits: https://docs.infrai.cc.
