"""Register all version 1 API and page routers."""
from fastapi import APIRouter

from server.app.api.v1 import (
    admin,
    admin_analytics,
    auth,
    chat,
    conversations,
    files,
    pages,
    user,
)

router = APIRouter()
router.include_router(auth.router)
router.include_router(conversations.router)
router.include_router(files.router)
router.include_router(chat.router)
router.include_router(pages.router)
router.include_router(admin.router)
router.include_router(admin_analytics.router)
router.include_router(user.router)
