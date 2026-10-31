"""接口：安装向导、登录、设置（密钥遮挡与加密存储）、推送渠道、各期与公开只读页。"""
import time

from fastapi.testclient import TestClient

from app import digest, notify, prefs
from app.main import app
from app.models import Setting
from fake import FakeFreshRSS, item


def login(c):
    if not c.get("/api/auth/status").json()["initialized"]:
        r = c.post("/api/auth/setup", json={"username": "admin", "password": "secret1"})
        assert r.status_code == 200
    tok = c.post("/api/auth/login", json={"username": "admin", "password": "secret1"}).json()["token"]
    return {"Authorization": "Bearer " + tok}


def test_auth_flow(db):
    with TestClient(app) as c:
        assert c.get("/api/overview").status_code == 401
        assert c.get("/api/setup/status").json()["configured"] is True
        h = login(c)
        assert c.post("/api/auth/setup", json={"username": "x", "password": "secret2"}).status_code == 400
        assert c.post("/api/auth/login", json={"username": "admin", "password": "bad"}).status_code == 401
        assert c.get("/api/auth/me", headers=h).json() == {"username": "admin"}
        r = c.post("/api/auth/password", json={"old_password": "secret1", "new_password": "secret9"}, headers=h).json()
        assert c.get("/api/auth/me", headers=h).status_code == 401          # 旧令牌失效
        assert c.get("/api/auth/me", headers={"Authorization": "Bearer " + r["token"]}).status_code == 200


def test_settings_mask_and_encrypt(db):
    with TestClient(app) as c:
        h = login(c)
        r = c.put("/api/settings/freshrss", headers=h, json={"url": "https://rss.example.com/", "username": "me",
                                                             "api_password": "supersecret", "categories": ["科技"]}).json()
        assert r["api_password"] == "supe…" and r["url"] == "https://rss.example.com"
        raw = db.get(Setting, "freshrss").value
        assert "supersecret" not in raw and "enc:" in raw
        # 原样提交遮挡值：沿用原密码
        c.put("/api/settings/freshrss", headers=h, json={**r, "categories": []})
        assert prefs.get("freshrss")["api_password"] == "supersecret"
        # 改了地址还提交遮挡值：拒绝，免得把密码送到别的服务器
        bad = c.put("/api/settings/freshrss", headers=h, json={**r, "url": "https://evil.example.com"})
        assert bad.status_code == 400 and "重新填写" in bad.json()["detail"]

        r = c.put("/api/settings/ai", headers=h, json={"enabled": False, "base_url": "https://api.deepseek.com/v1",
                                                       "api_key": "sk-1234567890", "model": "deepseek-chat"}).json()
        assert r["api_key"] == "sk-1…" and prefs.get("ai")["api_key"] == "sk-1234567890"
        assert c.put("/api/settings/ai", headers=h, json={"enabled": True, "base_url": "", "api_key": "", "model": ""}).status_code == 400

        s = c.put("/api/settings/schedule", headers=h, json={"morning_on": True, "morning": "07:30", "evening_on": True,
                                                             "evening": "07:30", "per_category": 10})
        assert s.status_code == 400
        s = c.put("/api/settings/schedule", headers=h, json={"morning_on": True, "morning": "07:30", "evening_on": False,
                                                             "evening": "20:00", "per_category": 5}).json()
        assert s["morning"] == "07:30" and s["per_category"] == 8
        assert c.put("/api/settings/site", headers=h, json={"public_url": "news.me", "retention_days": 10}).status_code == 400


def test_notify_channels(db, monkeypatch):
    with TestClient(app) as c:
        h = login(c)
        r = c.put("/api/notify", headers=h, json={"config": {"bark": {"enabled": True, "urls": ["https://api.day.app/KEY1234567890abc"]}}})
        assert r.status_code == 200 and r.json()["enabled"] == ["bark"]
        assert r.json()["config"]["bark"]["urls"][0].endswith("…")
        raw = db.get(Setting, "notify_config").value
        assert "KEY1234567890abc" not in raw
        assert notify.load_config()["bark"]["urls"] == ["https://api.day.app/KEY1234567890abc"]
        bad = c.put("/api/notify", headers=h, json={"config": {"telegram": {"enabled": True}}})
        assert bad.status_code == 400 and "bot_token" in bad.json()["detail"]
        sent = []
        monkeypatch.setattr(notify, "send_one", lambda t, cfg, title, text: sent.append((t, cfg["urls"])))
        assert c.post("/api/notify/test", headers=h, json={"channel": "bark", "config": r.json()["config"]["bark"]}).json()["ok"]
        assert sent == [("bark", ["https://api.day.app/KEY1234567890abc"])]


def test_issues_and_public_page(db, monkeypatch):
    prefs.put(db, "freshrss", {"url": "https://rss.example.com", "username": "me", "api_password": "apipass", "categories": []})
    prefs.put(db, "site", {"public_url": "https://news.me", "retention_days": 10})
    notify.save_config(db, {"bark": {"enabled": True, "urls": ["https://api.day.app/K"]}})
    db.commit()
    sent = []
    monkeypatch.setattr(notify, "_send_rich", lambda t, c, title, text, fmt: sent.append((title, text)))
    fake = FakeFreshRSS([item(i, int(time.time()) - 600 + i) for i in range(1, 4)])
    it = digest.run(db, "manual", client=fake.client())
    assert sent and sent[0][0].startswith("我的新闻 · 即时推送") and f"https://news.me/i/{it.id}?t={it.token}" in sent[0][1]
    with TestClient(app) as c:
        h = login(c)
        lst = c.get("/api/issues", headers=h).json()
        assert lst[0]["id"] == it.id and lst[0]["deliveries"][0] == {"channel": "bark", "ok": True, "error": None}
        full = c.get(f"/api/issues/{it.id}", headers=h).json()
        assert full["total"] == 3 and full["link"].endswith(it.token) and full["sections"][0]["category"] == "科技"
        assert c.get(f"/api/public/issues/{it.id}", params={"t": "wrongtoken"}).status_code == 404
        pub = c.get(f"/api/public/issues/{it.id}", params={"t": it.token}).json()
        assert pub["total"] == 3 and "token" not in pub and "deliveries" not in pub
        assert pub["highlights"] == full["highlights"]
        r = c.post(f"/api/issues/{it.id}/repush", headers=h, json={"channels": ["bark"]}).json()
        assert r["status"] == "sent" and len(sent) == 2
        ov = c.get("/api/overview", headers=h).json()
        assert ov["freshrss"] is True and ov["channels"] == ["bark"] and ov["last"]["id"] == it.id


def test_push_requires_config(db):
    with TestClient(app) as c:
        h = login(c)
        r = c.post("/api/issues/push", headers=h, json={"kind": "manual"})
        assert r.status_code == 400 and "FreshRSS" in r.json()["detail"]
        assert c.post("/api/issues/preview", headers=h, json={"kind": "manual"}).status_code == 400


def test_local_mode_ignores_legacy_settings(db, monkeypatch):
    from app import ai
    monkeypatch.setattr(ai, "summarize", lambda *a, **kw: (_ for _ in ()).throw(AssertionError("AI called")))
    prefs.put(db, "ai", {"enabled": True, "api_key": "legacy-key"})
    prefs.put(db, "schedule", {"per_category": 50})
    db.commit()
    with TestClient(app) as c:
        h = login(c)
        assert c.get("/api/settings/schedule", headers=h).json()["per_category"] == 8
        assert c.get("/api/settings/ai", headers=h).json()["enabled"] is False
        assert c.get("/api/overview", headers=h).json()["ai"] is False
        assert c.put("/api/settings/ai", headers=h, json={"enabled": True}).status_code == 400
        assert c.post("/api/settings/ai/test", headers=h, json={}).status_code == 400
