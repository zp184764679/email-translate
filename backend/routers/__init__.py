from .emails import router as emails_router
from .users import router as users_router
from .translate import router as translate_router
from .approval import router as drafts_router
from .suppliers import router as suppliers_router
from .signatures import router as signatures_router
from .labels import router as labels_router
from .folders import router as folders_router
from .calendar import router as calendar_router
from .ai_extract import router as ai_extract_router
from .tasks import router as tasks_router
from .rules import router as rules_router
from .approval_groups import router as approval_groups_router

__all__ = ["emails_router", "users_router", "translate_router", "drafts_router", "suppliers_router", "signatures_router", "labels_router", "folders_router", "calendar_router", "ai_extract_router", "tasks_router", "rules_router", "approval_groups_router"]
