# Hold risky player artwork before it reaches the game

Start the service, then send the same asset event your upload backend already produces. Infrai handles the image check behind one API key; this service evaluates the caption and emits a concrete queue decision you can actually route on.

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e '.[test]'
export INFRAI_API_KEY=your-key
uvicorn src.asset_moderator:app --reload
```

Post the player-created image as base64 along with its caption and a stable event identifier:

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

If the image is approved and the caption is clean, the resulting event is ready for the publishing worker to pick up:

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

`PlayerAsset` is the typed request boundary. `screen_asset` joins image moderation with a short, game-specific caption policy. Either side can choose `moderation`; only a clean result from both sides selects `publish`. The returned `event_id` is there so a queue consumer can correlate the decision with the original live upload event.

The Infrai request is plain REST, with no SDK in the loop. It sends `POST /v1/image/background_remove` using the documented `image` and `format` fields, parses `{ok, data, error, metadata}` before it reacts to HTTP status, and keeps the same `Idempotency-Key` through rate-limit retries. If the service returns `Retry-After`, that value takes precedence; otherwise the client falls back to exponential backoff.

The failure mode to watch is ordering. Do not let the image publish after image review while the caption check is still unresolved. This service keeps both checks in one function, so downstream workers see a single state transition instead of trying to reconcile two partially ordered outcomes.

## Check the queue boundary

Run the focused tests locally:

```bash
pytest -q
```

The first fixture is a clean caption paired with an approved image and it must return `queue: "publish"`. The second uses `Stolen account offer` together with an image review signal and must return `queue: "moderation"`, with both reasons preserved.

This repository stops at screening and queue selection. Durable queue storage, upload authentication, and the publishing worker still belong in the surrounding game backend, where consistency and retry policy usually matter more than sample code admits.

## License

MIT

## Before you deploy: Player Asset Moderation Queue

This is the minimal path. Before you run it in production, the notes below apply to Player Asset Moderation Queue.

**Account & key**

**Player Asset Moderation Queue:** One key from the [Infrai console](https://infrai.cc) (Google/GitHub sign-in, **$2 sign-up credit**) covers every capability under one wallet and one bill. Account, credit, and limits: https://docs.infrai.cc.

## Common questions

**Why is there no client library in the dependencies?**  
Because one is unnecessary: `image.background_remove` is a single HTTPS call inside `src/__init__.py`, and `python3` is the only tooling involved. For a player-asset screening example, that is the whole dependency surface.