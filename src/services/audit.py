from uuid import uuid4
from src.db.models import Audit
from src.core.security import now
from src.core.logging import logger

def audit(db, category, message, actor=None, request_id=None, level='INFO'):
    row = Audit(id=str(uuid4()), created=now(), category=category, message=message[:500], actor=actor, request_id=request_id, level=level)
    db.add(row)
    logger.log(30 if level == 'WARNING' else 20, '%s %s actor=%s request=%s', category, message[:500], actor, request_id)
    return row
