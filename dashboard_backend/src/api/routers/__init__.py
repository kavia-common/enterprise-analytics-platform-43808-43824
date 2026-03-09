from src.api.routers.dashboards import router as dashboards_router
from src.api.routers.widgets import router as widgets_router
from src.api.routers.saved_views import router as saved_views_router
from src.api.routers.ingestion import router as ingestion_router
from src.api.routers.behavior_analytics import router as behavior_analytics_router
from src.api.routers.observability import router as observability_router
from src.api.routers.realtime import router as realtime_router

__all__ = [
    "dashboards_router",
    "widgets_router",
    "saved_views_router",
    "ingestion_router",
    "behavior_analytics_router",
    "observability_router",
    "realtime_router",
]
