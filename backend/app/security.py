"""登录与首次设置：单个管理员账号、JWT 登录令牌、登录限速、安装码。做法同 ROS-DPI，去掉了多用户和角色。"""
import hmac
import ipaddress
import secrets
import time

from fastapi import Depends, HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt
from passlib.context import CryptContext

from app import database
from app.config import get_settings
from app.models import Setting, User

pwd = CryptContext(schemes=["bcrypt"], deprecated="auto")
_bearer = HTTPBearer(auto_error=False)
_secret: str | None = None
TOKEN_DAYS = 30


def secret_key() -> str:
    """JWT 签名、敏感字段加密共用的密钥：环境变量 SECRET_KEY，没有就首次启动随机生成存进数据库"""
    global _secret
    if _secret:
        return _secret
    if get_settings().secret_key:
        _secret = get_settings().secret_key
        return _secret
    with database.session() as db:
        row = db.get(Setting, "secret_key")
        if row is None:
            row = Setting(key="secret_key", value=secrets.token_urlsafe(48))
            db.add(row)
            db.commit()
        _secret = row.value
    return _secret


def forget_secret():
    """换数据库后（测试 / 安装向导）重新读取密钥"""
    global _secret
    _secret = None


def ensure_admin():
    """设置了 ADMIN_PASSWORD 且还没有账号时，创建 admin。"""
    pw = get_settings().admin_password
    with database.session() as db:
        if pw and db.query(User).count() == 0:
            db.add(User(username="admin", password_hash=pwd.hash(pw), created=int(time.time())))
            db.commit()
            print("[auth] 已按 ADMIN_PASSWORD 创建管理员 admin", flush=True)


def make_token(username: str, version: int | None = None) -> str:
    return jwt.encode({"sub": username, "ver": version or 0,
                       "exp": int(time.time()) + TOKEN_DAYS * 86400}, secret_key(), "HS256")


_versions: dict[str, tuple[int | None, float]] = {}   # username -> (token_version，账号不存在为 None, 缓存时间)


def _token_version(username: str) -> int | None:
    hit = _versions.get(username)
    if hit and time.time() - hit[1] < 30:
        return hit[0]
    with database.session() as db:
        u = db.query(User).filter(User.username == username).first()
    v = (u.token_version or 0) if u else None
    _versions[username] = (v, time.time())
    return v


def forget_versions():
    _versions.clear()


def current_user(cred: HTTPAuthorizationCredentials | None = Depends(_bearer)) -> str:
    if cred is None:
        raise HTTPException(401, "未登录")
    try:
        data = jwt.decode(cred.credentials, secret_key(), algorithms=["HS256"])
    except JWTError:
        raise HTTPException(401, "登录已过期，请重新登录")
    user = data.get("sub")
    ver = _token_version(user) if user else None
    if ver is None:
        raise HTTPException(401, "账号不存在，请重新登录")
    if data.get("ver", 0) != ver:
        raise HTTPException(401, "密码已修改，请重新登录")
    return user


def client_ip(request: Request | None) -> str:
    """反向代理后面取 X-Forwarded-For 最右边一跳（代理自己追加的那个），直连取 TCP 对端"""
    if request is None:
        return ""
    peer = request.client.host if request.client else ""
    fwd = request.headers.get("x-forwarded-for")
    if fwd and _is_private(peer):
        return fwd.split(",")[-1].strip()
    return peer


def _is_private(ip: str) -> bool:
    try:
        a = ipaddress.ip_address(ip)
    except ValueError:
        return False
    return a.is_private or a.is_loopback or a.is_link_local


# ---------------- 登录限速：同一 IP + 用户名连续失败 5 次后锁定 15 分钟 ----------------
MAX_LOGIN_FAILS = 5
LOGIN_LOCK_SECONDS = 900
_login_fails: dict[tuple[str, str], list] = {}


def check_login_lock(request: Request, username: str):
    key = (client_ip(request), username)
    e = _login_fails.get(key)
    if not e or e[0] < MAX_LOGIN_FAILS:
        return
    if time.time() < e[1]:
        raise HTTPException(429, f"失败次数过多，请 {max(int((e[1] - time.time()) / 60), 1)} 分钟后再试")
    _login_fails.pop(key, None)


def note_login_fail(request: Request, username: str):
    if len(_login_fails) > 10_000:
        for k in list(_login_fails)[:1000]:
            _login_fails.pop(k, None)
    key = (client_ip(request), username)
    e = _login_fails.get(key) or [0, 0.0]
    e[0] += 1
    if e[0] >= MAX_LOGIN_FAILS:
        e[1] = time.time() + LOGIN_LOCK_SECONDS
    _login_fails[key] = e


def note_login_ok(request: Request, username: str):
    _login_fails.pop((client_ip(request), username), None)


# ---------------- 首次设置的安装码 ----------------
# 安装向导和创建管理员的接口在设置完成前不需要登录：谁先打开网页谁就能接管实例。
# 从公网地址访问时要填启动日志里打印的一次性安装码；内网访问不需要
_setup_code = secrets.token_hex(4)


def setup_code() -> str:
    return _setup_code


def check_setup_code(request: Request):
    ip = client_ip(request)
    try:
        if _is_private(ip) or not ip:
            return
        ipaddress.ip_address(ip)
    except ValueError:
        return   # 测试客户端等没有真实地址的情况
    code = (request.headers.get("x-setup-code") or "").strip().lower()
    if not hmac.compare_digest(code, _setup_code):
        raise HTTPException(403, "setup_code_required")
