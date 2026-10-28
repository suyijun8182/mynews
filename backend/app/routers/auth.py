import time

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Setting, User
from app.security import (check_login_lock, check_setup_code, current_user, forget_versions, make_token,
                          note_login_fail, note_login_ok, pwd)

router = APIRouter(prefix="/api/auth", tags=["auth"])


class Creds(BaseModel):
    username: str = "admin"
    password: str = Field(min_length=1)


class SetupReq(BaseModel):
    username: str = Field("admin", min_length=1, max_length=64, pattern=r"^[A-Za-z0-9_.@-]+$")
    password: str = Field(min_length=6, max_length=128)


class PwChange(BaseModel):
    old_password: str
    new_password: str = Field(min_length=6, max_length=128)


@router.get("/status")
def status(db: Session = Depends(get_db)):
    return {"initialized": db.query(User).count() > 0}


@router.post("/setup")
def setup(req: SetupReq, request: Request, db: Session = Depends(get_db)):
    """安装向导第二步：设置管理员账号（只能设一次）"""
    if db.query(User).count() > 0:
        raise HTTPException(400, "管理员已存在")
    check_setup_code(request)
    u = User(username=req.username, password_hash=pwd.hash(req.password), created=int(time.time()))
    db.add(u)
    # settings 主键唯一：两个请求同时走到这里时只有一个能提交成功（防安装窗口期被并发接管）
    db.add(Setting(key="setup_done", value=str(int(time.time()))))
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(400, "管理员已存在")
    forget_versions()
    return {"token": make_token(u.username, u.token_version), "username": u.username}


@router.post("/login")
def login(req: Creds, request: Request, db: Session = Depends(get_db)):
    check_login_lock(request, req.username)
    u = db.query(User).filter(User.username == req.username).first()
    if not u or not pwd.verify(req.password, u.password_hash):
        note_login_fail(request, req.username)
        raise HTTPException(401, "用户名或密码错误")
    note_login_ok(request, req.username)
    u.last_login = int(time.time())
    db.commit()
    return {"token": make_token(u.username, u.token_version), "username": u.username}


@router.get("/me")
def me(user: str = Depends(current_user)):
    return {"username": user}


@router.post("/password")
def change_password(req: PwChange, user: str = Depends(current_user), db: Session = Depends(get_db)):
    u = db.query(User).filter(User.username == user).first()
    if not u or not pwd.verify(req.old_password, u.password_hash):
        raise HTTPException(400, "原密码错误")
    u.password_hash = pwd.hash(req.new_password)
    u.token_version = (u.token_version or 0) + 1   # 其它设备上的旧登录立即失效
    db.commit()
    forget_versions()
    return {"ok": True, "token": make_token(user, u.token_version), "username": user}
