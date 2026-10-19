"""仅接受 Bearer 凭据的管理接口依赖。"""
import secrets
from fastapi import Header, HTTPException
from src.core.config import settings


def require_admin(authorization: str | None = Header(None)) -> None:
    expected=settings.ingestion_trigger_token
    supplied=authorization[7:] if authorization and authorization.startswith('Bearer ') else ''
    if not expected or not supplied or not secrets.compare_digest(expected.encode(),supplied.encode()):
        raise HTTPException(403,'Invalid token')
