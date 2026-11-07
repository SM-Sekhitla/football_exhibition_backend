import json
import logging
from logging.handlers import RotatingFileHandler
from src.core.config import settings

class JsonFormatter(logging.Formatter):
    def format(self, record):
        return json.dumps({'time': self.formatTime(record), 'level': record.levelname, 'message': record.getMessage()})

def configure_logging():
    settings.log_dir.mkdir(parents=True, exist_ok=True)
    logger = logging.getLogger('best5')
    logger.setLevel(settings.log_level)
    if not logger.handlers:
        handler = RotatingFileHandler(settings.log_dir / 'backend.log', maxBytes=5_000_000, backupCount=5)
        handler.setFormatter(JsonFormatter())
        logger.addHandler(handler)
        if settings.log_console: logger.addHandler(logging.StreamHandler())
    return logger

logger = logging.getLogger('best5')
