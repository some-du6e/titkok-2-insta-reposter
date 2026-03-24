import flask
import os
from src.components import captions as captions_store
from src.components.captions import CaptionPayloadError
from src.components.pipeline import (
    QueuePipelineError,
    QueueValidationError,
    enqueue_tiktok_url,
    list_queue_items,
    publish_queue_item,
    retry_queue_item,
)
from src.components.queue_store import QueueItemNotFoundError
# init that shi
www_dir = os.path.join(os.path.dirname(__file__), '..', 'www')
app = flask.Flask(__name__)

# serve www (prob gonna replaced with react)
@app.route('/',)
def serve_index():
    return flask.send_from_directory(www_dir, "index.html")

@app.route('/<path:filename>')
def serve_custom_file(filename):
    return flask.send_from_directory(www_dir, filename)


@app.route("/api/captions", methods=["GET"])
def get_captions():
    try:
        return flask.jsonify({"captions": captions_store.load_captions()})
    except Exception as e:
        return flask.jsonify({"error": str(e)}), 500


@app.route("/api/captions", methods=["POST"])
def save_captions():
    payload = flask.request.get_json(silent=True)

    if not isinstance(payload, dict) or "captions" not in payload:
        return flask.jsonify({"error": "Request body must be JSON with a captions field"}), 400

    try:
        captions = captions_store.save_captions(payload["captions"])
        return flask.jsonify({"captions": captions, "saved": True})
    except CaptionPayloadError as e:
        return flask.jsonify({"error": str(e)}), 400
    except Exception as e:
        return flask.jsonify({"error": str(e)}), 500


@app.route("/api/upload", methods=["POST"])
def upload_video():
    import src.components.video_logic.uploadvideo as video_logic
    video_path = flask.request.form.get("video_path")
    caption = flask.request.form.get("caption", "")
    media_type = flask.request.form.get("media_type", "REELS")
    if not video_path:
        return flask.jsonify({"error": "Missing video_path parameter"}), 400
    try:
        result = video_logic.InstagramUploader().upload_video(
            video_path=video_path,
            caption=caption,
            media_type=media_type,
        )
        return flask.jsonify(result)
    except Exception as e:
        return flask.jsonify({"error": str(e)}), 500


@app.route("/api/queue", methods=["GET"])
def get_queue():
    try:
        return flask.jsonify({"items": list_queue_items()})
    except Exception as e:
        return flask.jsonify({"error": str(e)}), 500


@app.route("/api/get_tiktok_link", methods=["POST"])
def get_tiktok_link():
    url = flask.request.form.get("url")
    if not url:
        return flask.jsonify({"error": "Missing url parameter"}), 400

    try:
        item = enqueue_tiktok_url(url)
        return flask.jsonify({"status": "queued", "item": item})
    except QueueValidationError as e:
        return flask.jsonify({"error": str(e)}), 400
    except QueuePipelineError as e:
        return flask.jsonify({"error": str(e)}), 500
    except Exception as e:
        return flask.jsonify({"error": str(e)}), 500


@app.route("/api/queue/<item_id>/publish", methods=["POST"])
def publish_queue(item_id):
    try:
        item = publish_queue_item(item_id)
        status_code = 200 if item.get("status") == "published" else 500
        return flask.jsonify({"item": item}), status_code
    except QueueValidationError as e:
        message = str(e)
        if "already published" in message.lower() or "missing" in message.lower():
            return flask.jsonify({"error": message}), 409
        return flask.jsonify({"error": message}), 400
    except QueuePipelineError as e:
        message = str(e)
        if "not found" in message.lower():
            return flask.jsonify({"error": message}), 404
        return flask.jsonify({"error": message}), 500
    except QueueItemNotFoundError:
        return flask.jsonify({"error": "Queue item not found"}), 404
    except Exception as e:
        return flask.jsonify({"error": str(e)}), 500


@app.route("/api/queue/<item_id>/retry", methods=["POST"])
def retry_queue(item_id):
    try:
        item = retry_queue_item(item_id)
        status_code = 200 if item.get("status") == "published" else 500
        return flask.jsonify({"item": item}), status_code
    except QueueValidationError as e:
        return flask.jsonify({"error": str(e)}), 409
    except QueuePipelineError as e:
        message = str(e)
        if "not found" in message.lower():
            return flask.jsonify({"error": message}), 404
        return flask.jsonify({"error": message}), 500
    except QueueItemNotFoundError:
        return flask.jsonify({"error": "Queue item not found"}), 404
    except Exception as e:
        return flask.jsonify({"error": str(e)}), 500

if __name__ == '__main__':
    app.run(debug=True, port=6767)


def runapi(debug=True, port=6767):
    app.run(debug=debug, port=port)
