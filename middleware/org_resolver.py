# middleware/org_resolver.py
from fastapi import Request, HTTPException
from starlette.middleware.base import BaseHTTPMiddleware
from jose import jwt, JWTError
from config import SECRET_KEY, ALGORITHM

PUBLIC_PATHS = {
    "/",
    "/start",
    "/admin",
    "/admin/dashboard",
    "/org/register",
    "/api/auth/login",
    "/api/auth/signup",
    "/api/auth/org/register",
    "/docs",
    "/openapi.json",
    "/redoc",
    "/favicon.ico",
}

class OrgResolverMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        path = request.url.path
        
        # Allow public paths + any path starting with /api/auth/organizations/
        if (path in PUBLIC_PATHS or 
            path.startswith("/static/") or 
            path.startswith("/api/auth/organizations/")):
            return await call_next(request)

        # Token check for all other paths
        auth_header = request.headers.get("Authorization")
        token = None
        if auth_header and auth_header.startswith("Bearer "):
            token = auth_header.split(" ")[1]
        else:
            token = request.query_params.get("token")

        if not token:
            raise HTTPException(status_code=401, detail="Missing token")

        try:
            payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
            org_short_id = payload.get("org_short_id")
            user_id = payload.get("sub")
            if not org_short_id or not user_id:
                raise HTTPException(status_code=401, detail="Invalid token")
            request.state.org_short_id = org_short_id
            request.state.user_id = int(user_id)
        except JWTError:
            raise HTTPException(status_code=401, detail="Invalid token")

        return await call_next(request)