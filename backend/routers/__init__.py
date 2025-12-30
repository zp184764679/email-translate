"""
路由器模块导出

命名说明:
- drafts_router: 来自 approval.py，处理草稿和审批功能 (历史命名，保持兼容)
- approval_groups_router: 来自 approval_groups.py，处理审批人组管理
"""
from .emails import router as emails_router
from .users import router as users_router
from .translate import router as translate_router
from .approval import router as drafts_router  # 草稿/审批路由 (文件名 approval.py)
from .suppliers import router as suppliers_router
from .signatures import router as signatures_router
from .labels import router as labels_router
from .folders import router as folders_router
from .calendar import router as calendar_router
from .ai_extract import router as ai_extract_router
from .tasks import router as tasks_router
from .rules import router as rules_router
from .approval_groups import router as approval_groups_router
from .task_extractions import router as task_extractions_router
from .dashboard import router as dashboard_router
from .notifications import router as notifications_router
from .templates import router as templates_router
from .archive import router as archive_router
from .classification import router as classification_router
from .statistics import router as statistics_router

__all__ = [
    "emails_router",
    "users_router",
    "translate_router",
    "drafts_router",
    "suppliers_router",
    "signatures_router",
    "labels_router",
    "folders_router",
    "calendar_router",
    "ai_extract_router",
    "tasks_router",
    "rules_router",
    "approval_groups_router",
    "task_extractions_router",
    "dashboard_router",
    "notifications_router",
    "templates_router",
    "archive_router",
    "classification_router",
    "statistics_router",
]
