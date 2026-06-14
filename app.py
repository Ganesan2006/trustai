# app.py
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from routers import auth, conversations, files, chat, pages, admin_analytics, admin, user   # <-- ADD user
from middleware.org_resolver import OrgResolverMiddleware

app = FastAPI(title="RAG Chat API")
app.add_middleware(OrgResolverMiddleware)
app.mount("/static", StaticFiles(directory="static"), name="static")

app.include_router(auth.router)
app.include_router(conversations.router)
app.include_router(files.router)
app.include_router(chat.router)
app.include_router(pages.router)
app.include_router(admin.router)
app.include_router(admin_analytics.router)
app.include_router(user.router)   # <-- ADD THIS LINE