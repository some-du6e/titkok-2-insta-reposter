from src.components.api import app
from src.components.queue_worker import start_queue_worker


start_queue_worker(debug=False)
