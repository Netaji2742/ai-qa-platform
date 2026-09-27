"""
JWT-based authentication and a minimal RBAC dependency.

Production note: this module stands in for a real Identity Provider. See
ARCHITECTURE.md section 2 for how this would be extended to a full
SSO/OIDC flow (Authorization Code + PKCE against an external IdP, with
this API validating IdP-issued JWTs instead of minting its own).
"""
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt
from passlib.context import CryptContext

from app.config import get_settings

settings = get_settings()
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


class Bearer401(HTTPBearer):
    """HTTPBearer defaults to 403 when no Authorization header is present
    at all, which is the wrong status code (403 implies an authenticated
    but disallowed request; missing credentials is 401). This subclass
    corrects that to 401 to match standard REST semantics."""

    async def __call__(self, request: Request) -> HTTPAuthorizationCredentials:
        try:
            return await super().__call__(request)
        except HTTPException as exc:
            if exc.status_code == status.HTTP_403_FORBIDDEN:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail=exc.detail,
                    headers={"WWW-Authenticate": "Bearer"},
                )
            raise


# HTTPBearer (not OAuth2PasswordBearer) so the Swagger "Authorize" dialog
# just takes a pasted token, matching how /auth/login actually works (a
# plain JSON body, not the OAuth2 form-encoded password flow).
bearer_scheme = Bearer401()


def verify_password(plain_password: str, hashed_password: str) -> bool:
    return pwd_context.verify(plain_password, hashed_password)


def hash_password(plain_password: str) -> str:
    return pwd_context.hash(plain_password)


def authenticate_user(username: str, password: str) -> Optional[dict]:
    """Stand-in for a real user lookup (Postgres table / IdP). Only one
    demo user is configured, via environment variables — no hard-coded
    credentials in source."""
    if username != settings.DEMO_USERNAME:
        return None
    if not verify_password(password, settings.DEMO_PASSWORD_HASH):
        return None
    return {"username": username, "role": settings.DEMO_ROLE}


def create_access_token(data: dict) -> str:
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + timedelta(
        minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES
    )
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)


def decode_access_token(token: str) -> dict:
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(
            token, settings.JWT_SECRET_KEY, algorithms=[settings.JWT_ALGORITHM]
        )
        username: str = payload.get("sub")
        if username is None:
            raise credentials_exception
        return payload
    except JWTError:
        raise credentials_exception


def get_current_user(creds: HTTPAuthorizationCredentials = Depends(bearer_scheme)) -> dict:
    payload = decode_access_token(creds.credentials)
    return {"username": payload.get("sub"), "role": payload.get("role", "user")}


def require_role(*allowed_roles: str):
    """RBAC dependency factory. Usage: Depends(require_role("admin"))."""

    def _check(user: dict = Depends(get_current_user)) -> dict:
        if user["role"] not in allowed_roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Role '{user['role']}' is not permitted to access this resource",
            )
        return user

    return _check
