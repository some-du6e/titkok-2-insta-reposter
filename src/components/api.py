import os

import flask
from dotenv import load_dotenv

from src.components import captions as captions_store
from src.components.captions import CaptionPayloadError
from src.components.public_collection import (
    get_public_collection_status,
    sync_public_collection,
    test_public_collection_url,
)
from src.components.pipeline import (
    QueuePipelineError,
    QueueValidationError,
    enqueue_tiktok_url,
    get_queue_state,
    list_queue_items,
    publish_next_queued_item,
    publish_queue_item,
    retry_queue_item,
    update_queue_settings,
)
from src.components.preview_service import PreviewGenerationError, build_preview_response
from src.components.queue_store import PROJECT_ROOT, QueueItemNotFoundError
from src.components.queue_worker import start_queue_worker
from src.components.system_update import (
    SystemUpdateError,
    run_system_restart,
    run_system_update,
)


load_dotenv()

# init that shi
www_dir = os.path.join(os.path.dirname(__file__), "..", "www")
app = flask.Flask(__name__)


def _json_error(message: str, status_code: int):
    return flask.jsonify({"error": message}), status_code


# serve www (prob gonna replaced with react)
@app.route("/")
def serve_index():
    return flask.send_from_directory(www_dir, "index.html")


@app.route("/<path:filename>")
def serve_custom_file(filename):
    return flask.send_from_directory(www_dir, filename)


@app.route("/api/captions", methods=["GET"])
def get_captions():
    try:
        return flask.jsonify({"captions": captions_store.load_captions()})
    except Exception as e:
        return _json_error(str(e), 500)


@app.route("/api/captions", methods=["POST"])
def save_captions():
    payload = flask.request.get_json(silent=True)

    if not isinstance(payload, dict) or "captions" not in payload:
        return _json_error("Request body must be JSON with a captions field", 400)

    try:
        captions = captions_store.save_captions(payload["captions"])
        return flask.jsonify({"captions": captions, "saved": True})
    except CaptionPayloadError as e:
        return _json_error(str(e), 400)
    except Exception as e:
        return _json_error(str(e), 500)


@app.route("/api/upload", methods=["POST"])
def upload_video():
    import src.components.video_logic.uploadvideo as video_logic

    video_path = flask.request.form.get("video_path")
    caption = flask.request.form.get("caption", "")
    media_type = flask.request.form.get("media_type", "REELS")
    cover_image_path = flask.request.form.get("cover_image_path")
    thumb_offset = flask.request.form.get("thumb_offset", type=int)
    share_to_feed = flask.request.form.get("share_to_feed", type=lambda v: str(v).lower() in {"1", "true", "yes"})
    if not video_path:
        return _json_error("Missing video_path parameter", 400)
    try:
        result = video_logic.InstagramUploader().upload_video(
            video_path=video_path,
            caption=caption,
            media_type=media_type,
            cover_image_path=cover_image_path,
            thumb_offset=thumb_offset,
            share_to_feed=share_to_feed,
        )
        return flask.jsonify(result)
    except Exception as e:
        return _json_error(str(e), 500)


@app.route("/api/cover-image", methods=["POST"])
def upload_cover_image():
    cover_image = flask.request.files.get("cover_image")
    if cover_image is None or not cover_image.filename:
        return _json_error("Missing cover_image file", 400)

    content_type = (cover_image.mimetype or "").lower()
    if content_type and not content_type.startswith("image/"):
        return _json_error("cover_image must be an image file", 400)

    destination_path = PROJECT_ROOT / "coverrrr.png"
    try:
        cover_image.save(destination_path)
    except Exception as e:
        return _json_error(f"Failed to save cover image: {e}", 500)

    return flask.jsonify({"saved": True, "path": str(destination_path), "filename": destination_path.name})


@app.route("/api/queue", methods=["GET"])
def get_queue():
    try:
        state = get_queue_state()
        return flask.jsonify({"items": state["items"], "settings": state["settings"]})
    except Exception as e:
        return _json_error(str(e), 500)


@app.route("/api/queue/<item_id>/preview", methods=["GET"])
def get_queue_preview(item_id):
    try:
        image_path, _item = build_preview_response(item_id)
        response = flask.send_file(image_path, mimetype="image/jpeg")
        response.headers["Cache-Control"] = "public, max-age=86400"
        return response
    except QueueItemNotFoundError:
        return _json_error("Queue item not found", 404)
    except FileNotFoundError as e:
        return _json_error(str(e), 404)
    except PreviewGenerationError as e:
        return _json_error(str(e), 500)
    except Exception as e:
        return _json_error(str(e), 500)


@app.route("/api/queue/settings", methods=["POST"])
def save_queue_settings():
    payload = flask.request.get_json(silent=True)
    if not isinstance(payload, dict):
        return _json_error("Request body must be a JSON object", 400)

    try:
        settings = update_queue_settings(payload)
        return flask.jsonify({"settings": settings})
    except QueueValidationError as e:
        return _json_error(str(e), 400)
    except Exception as e:
        return _json_error(str(e), 500)


@app.route("/api/queue/run-next", methods=["POST"])
def run_next_queue_item():
    try:
        result = publish_next_queued_item(is_auto=True)
        status_code = 200
        item = result.get("item")
        if item and item.get("status") == "failed":
            status_code = 500
        return flask.jsonify(result), status_code
    except QueueValidationError as e:
        return _json_error(str(e), 409)
    except QueuePipelineError as e:
        return _json_error(str(e), 500)
    except Exception as e:
        return _json_error(str(e), 500)


@app.route("/api/public-collection/status", methods=["GET"])
def public_collection_status():
    try:
        return flask.jsonify(get_public_collection_status())
    except Exception as e:
        return _json_error(str(e), 500)


@app.route("/api/public-collection/test", methods=["POST"])
def test_public_collection():
    payload = flask.request.get_json(silent=True)
    if not isinstance(payload, dict):
        return _json_error("Request body must be a JSON object", 400)

    url = payload.get("url")
    if not isinstance(url, str) or not url.strip():
        return _json_error("Missing url parameter", 400)

    try:
        result = test_public_collection_url(url)
        status_code = 200 if result.get("fetch_ok") else 400
        return flask.jsonify(result), status_code
    except Exception as e:
        return _json_error(str(e), 500)


@app.route("/api/public-collection/sync", methods=["POST"])
def sync_public_collection_route():
    payload = flask.request.get_json(silent=True)
    override_url = None
    if payload is not None:
        if not isinstance(payload, dict):
            return _json_error("Request body must be a JSON object", 400)
        override_url = payload.get("url")
        if override_url is not None and (not isinstance(override_url, str) or not override_url.strip()):
            return _json_error("url must be a non-empty string", 400)

    try:
        result = sync_public_collection(override_url=override_url)
        status_code = 200 if not result.get("error") else 400
        return flask.jsonify(result), status_code
    except QueueValidationError as e:
        return _json_error(str(e), 400)
    except QueuePipelineError as e:
        return _json_error(str(e), 500)
    except Exception as e:
        return _json_error(str(e), 500)


@app.route("/api/system/update", methods=["POST"])
def update_system():
    try:
        return flask.jsonify(run_system_update())
    except SystemUpdateError as e:
        return (
            flask.jsonify(
                {
                    "error": str(e),
                    "stage": e.stage,
                    "stdout": e.stdout,
                    "stderr": e.stderr,
                }
            ),
            e.status_code,
        )
    except Exception as e:
        return _json_error(str(e), 500)


@app.route("/api/system/restart", methods=["POST"])
def restart_system():
    try:
        return flask.jsonify(run_system_restart())
    except SystemUpdateError as e:
        return (
            flask.jsonify(
                {
                    "error": str(e),
                    "stage": e.stage,
                    "stdout": e.stdout,
                    "stderr": e.stderr,
                }
            ),
            e.status_code,
        )
    except Exception as e:
        return _json_error(str(e), 500)


@app.route("/api/get_tiktok_link", methods=["POST"])
def get_tiktok_link():
    url = flask.request.form.get("url")
    if not url:
        return _json_error("Missing url parameter", 400)

    source_kind = flask.request.form.get("source_kind", "manual")
    discovered_at = flask.request.form.get("discovered_at")

    try:
        status, item = enqueue_tiktok_url(
            url,
            source_kind=source_kind,
            discovered_at=discovered_at,
            ingestion_metadata={
                "client": flask.request.form.get("client"),
                "monitor_tab_url": flask.request.form.get("monitor_tab_url"),
            },
        )
        payload = {"status": status, "item": item}
        if status == "duplicate":
            payload["message"] = "TikTok already exists in queue"
        return flask.jsonify(payload)
    except QueueValidationError as e:
        return _json_error(str(e), 400)
    except QueuePipelineError as e:
        return _json_error(str(e), 500)
    except Exception as e:
        return _json_error(str(e), 500)


@app.route("/api/queue/<item_id>/publish", methods=["POST"])
def publish_queue(item_id):
    try:
        item = publish_queue_item(item_id)
        status_code = 200 if item.get("status") == "published" else 500
        return flask.jsonify({"item": item}), status_code
    except QueueValidationError as e:
        message = str(e)
        if "already published" in message.lower() or "already publishing" in message.lower():
            return _json_error(message, 409)
        return _json_error(message, 400)
    except QueuePipelineError as e:
        message = str(e)
        if "not found" in message.lower():
            return _json_error(message, 404)
        return _json_error(message, 500)
    except QueueItemNotFoundError:
        return _json_error("Queue item not found", 404)
    except Exception as e:
        return _json_error(str(e), 500)


@app.route("/api/queue/<item_id>/retry", methods=["POST"])
def retry_queue(item_id):
    try:
        item = retry_queue_item(item_id)
        status_code = 200 if item.get("status") == "published" else 500
        return flask.jsonify({"item": item}), status_code
    except QueueValidationError as e:
        return _json_error(str(e), 409)
    except QueuePipelineError as e:
        message = str(e)
        if "not found" in message.lower():
            return _json_error(message, 404)
        return _json_error(message, 500)
    except QueueItemNotFoundError:
        return _json_error("Queue item not found", 404)
    except Exception as e:
        return _json_error(str(e), 500)


def _run_app(debug: bool, port: int):
    start_queue_worker(debug=debug)
    app.run(debug=debug, port=port)


if __name__ == "__main__":
    _run_app(debug=True, port=6767)


def runapi(debug=True, port=6767):
    _run_app(debug=debug, port=port)
