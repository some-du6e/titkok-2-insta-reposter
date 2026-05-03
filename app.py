import os

import src.components.api

if __name__ == "__main__":
    port = int(os.getenv("PORT", "6767"))
    host = os.getenv("HOST", "127.0.0.1")
    debug = os.getenv("FLASK_DEBUG", "").lower() in {"1", "true", "yes", "on"}
    src.components.api.runapi(debug=debug, host=host, port=port)
