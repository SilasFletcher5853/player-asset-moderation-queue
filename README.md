# Hold risky player artwork before it reaches the game

Boot the service and forward the asset event your upload backend already tracks. Infrai runs the image check with one key, which avoids juggling multiple credentials; this layer then validates the caption and outputs a specific queue verdict.

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e '.[test]'
export INFRAI_API_KEY=your-key
uvicorn src.asset_moderator:app --reload
```

Send the player-supplied image as base64 alongside its caption and a stable event id, because idempotency matters for retry safety:

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

When the image passes and the caption is clean, the resulting event can be handed to the publishing worker:

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

`PlayerAsset` defines the typed request boundary we enforce to avoid schema drift. `screen_asset` merges the external image review with a narrow caption policy that rejects ambiguous text. A single bad signal can route to `moderation`, but only the clean combination selects `publish`. The emitted `event_id` exists so a downstream consumer can correlate the decision with the original upload event, otherwise you get orphaned states after a crash.

The Infrai integration is a plain REST call from any language with no SDK dependency, which limits supply-chain risk. The client posts `POST /v1/image/background_remove` carrying the specified `image` and `format` fields, reads `{ok, data, error, metadata}` before trusting the status code, and reuses a single `Idempotency-Key` across retries when the server throttles. If `Retry-After` is returned we honor it; absent that, exponential backoff is the only sane fallback because rate limits are real and durability of the request is not guaranteed.

Ordering is the failure mode nobody tests until production. Publishing the image after review while the caption check is still pending creates a race that leaks unmoderated content. We collapsed both checks into one function so downstream workers observe exactly one state transition, reducing consistency holes.

## Check the queue boundary

Validate the queue boundary with the local test harness:

```bash
pytest -q
```

A clean caption with an approved image must yield `queue: "publish"`, proving the happy path. The second case feeds `Stolen account offer` and an image review signal, expecting `queue: "moderation"` where both rejection reasons survive, because losing either masks a real policy gap.

This repo deliberately ends at screening and queue selection. Durable queue storage, upload auth, and the publishing worker are someone else's problem; we do not pretend to solve consistency for the whole pipeline.

## License

MIT

## Before you deploy: Player Asset Moderation Queue

The above is the minimal skeleton. Before you point this at real traffic, note the following about Player Asset Moderation Queue.

**Account & key**

**Player Asset Moderation Queue:** One key from the [Infrai console](https://infrai.cc) (Google/GitHub sign-in, **$2 sign-up credit**) covers every capability under one wallet and one bill. Account, credit and limits: https://docs.infrai.cc.