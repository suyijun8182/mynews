"""网页上改的配置：存在 settings 表，每组一个 JSON。敏感字段加密后再存（同 EasySub：Fernet，密钥由 SECRET_KEY 派生）。

- freshrss  FreshRSS 连接：地址、用户名、API 密码、要汇总的分类（空 = 全部）
- schedule  早晚报：时间、开关、每个分类最多几条
- ai        AI 摘要：开关、OpenAI 兼容接口地址、API Key、模型
- site      外部访问地址（「查看全部」链接用）、数据保留天数
- notify_config  推送渠道（见 app.notify）

返回给前端时密钥只显示开头并以“…”结尾，保存时以“…”结尾的值沿用原值（同 app.notify 的做法）。
"""
import base64
import hashlib
import json

from cryptography.fernet import Fernet, InvalidToken

from app import database
from app.models import Setting

_PREFIX = "enc:"

DEFAULTS: dict[str, dict] = {
    "freshrss": {"url": "", "username": "", "api_password": "", "categories": []},
    "schedule": {"morning_on": True, "morning": "08:00", "evening_on": True, "evening": "20:00", "per_category": 8},
    "ai": {"enabled": False, "base_url": "https://api.deepseek.com/v1", "api_key": "", "model": "deepseek-chat"},
    "site": {"public_url": "", "retention_days": 10},
}
SECRETS = {"freshrss": {"api_password"}, "ai": {"api_key"}}


def _fernet() -> Fernet:
    from app.security import secret_key
    return Fernet(base64.urlsafe_b64encode(hashlib.sha256(secret_key().encode()).digest()))


def encrypt(value: str | None) -> str | None:
    if not value or value.startswith(_PREFIX):
        return value
    return _PREFIX + _fernet().encrypt(value.encode()).decode()


def decrypt(value: str | None) -> str | None:
    if not value or not value.startswith(_PREFIX):
        return value
    try:
        return _fernet().decrypt(value[len(_PREFIX):].encode()).decode()
    except (InvalidToken, ValueError):
        return ""   # 密钥换过：当作没填，让用户重新填写


def raw_get(key: str, default=None):
    if not database.is_configured():
        return default
    with database.session() as db:
        row = db.get(Setting, key)
    try:
        return json.loads(row.value) if row and row.value else default
    except ValueError:
        return default


def raw_set(db, key: str, value) -> None:
    v = json.dumps(value, ensure_ascii=False)
    row = db.get(Setting, key)
    if row is None:
        db.add(Setting(key=key, value=v))
    else:
        row.value = v


def get(group: str) -> dict:
    """一组配置（补齐默认值，敏感字段已解密）"""
    saved = raw_get(group, {}) or {}
    out = {**DEFAULTS[group], **{k: v for k, v in saved.items() if k in DEFAULTS[group]}}
    for k in SECRETS.get(group, ()):
        out[k] = decrypt(out.get(k)) or ""
    return out


def put(db, group: str, value: dict) -> dict:
    """保存一组配置：只留认识的字段，敏感字段以“…”结尾时沿用原值，加密后写库"""
    old = get(group)
    out = {**DEFAULTS[group], **{k: v for k, v in value.items() if k in DEFAULTS[group]}}
    for k in SECRETS.get(group, ()):
        v = out.get(k) or ""
        if isinstance(v, str) and v.endswith("…"):
            v = old.get(k) or ""
        out[k] = v
    raw_set(db, group, {k: (encrypt(v) if k in SECRETS.get(group, ()) else v) for k, v in out.items()})
    return out


def masked(group: str, value: dict | None = None) -> dict:
    v = dict(value if value is not None else get(group))
    for k in SECRETS.get(group, ()):
        s = v.get(k) or ""
        v[k] = (s[:4] + "…") if len(s) > 4 else ("…" if s else "")
    return v
