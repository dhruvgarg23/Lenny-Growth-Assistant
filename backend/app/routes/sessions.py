from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from app.services.database import get_db
from app.models.db import Session, Message
from app.models.schemas import SessionCreate, SessionOut, MessageOut

router = APIRouter(prefix="/sessions", tags=["sessions"])

@router.post("", response_model=SessionOut, status_code=201)
async def create_session(payload: SessionCreate, db: AsyncSession = Depends(get_db)):
    sess = Session(title=payload.title or "New chat")
    db.add(sess)
    await db.flush()
    return SessionOut(
        id=sess.id, title=sess.title, user_id=sess.user_id,
        created_at=sess.created_at.isoformat(), updated_at=sess.updated_at.isoformat(), message_count=0
    )

@router.get("", response_model=list[SessionOut])
async def list_sessions(db: AsyncSession = Depends(get_db)):
    q = await db.execute(select(Session).order_by(Session.updated_at.desc()).limit(50))
    sessions = q.scalars().all()
    out = []
    for s in sessions:
        cnt = await db.execute(select(func.count()).select_from(Message).where(Message.session_id == s.id))
        count = cnt.scalar() or 0
        out.append(SessionOut(
            id=s.id, title=s.title, user_id=s.user_id,
            created_at=s.created_at.isoformat(), updated_at=s.updated_at.isoformat(), message_count=count
        ))
    return out

@router.get("/{session_id}", response_model=SessionOut)
async def get_session(session_id: str, db: AsyncSession = Depends(get_db)):
    s = await db.get(Session, session_id)
    if not s:
        raise HTTPException(status_code=404, detail="Session not found")
    cnt = await db.execute(select(func.count()).select_from(Message).where(Message.session_id == s.id))
    count = cnt.scalar() or 0
    return SessionOut(
        id=s.id, title=s.title, user_id=s.user_id,
        created_at=s.created_at.isoformat(), updated_at=s.updated_at.isoformat(), message_count=count
    )

@router.delete("/{session_id}")
async def delete_session(session_id: str, db: AsyncSession = Depends(get_db)):
    s = await db.get(Session, session_id)
    if not s:
        raise HTTPException(status_code=404, detail="Session not found")
    await db.delete(s)
    return {"ok": True}

@router.get("/{session_id}/messages", response_model=list[MessageOut])
async def list_messages(session_id: str, db: AsyncSession = Depends(get_db)):
    s = await db.get(Session, session_id)
    if not s:
        raise HTTPException(status_code=404, detail="Session not found")
    q = await db.execute(select(Message).where(Message.session_id == session_id).order_by(Message.created_at.asc()))
    msgs = q.scalars().all()
    out = []
    for m in msgs:
        meta = m.meta or {}
        out.append(MessageOut(
            id=m.id, session_id=m.session_id, role=m.role, content=m.content,
            sources=meta.get("sources", []), artifact=meta.get("artifact"), meta=meta, created_at=m.created_at.isoformat()
        ))
    return out
