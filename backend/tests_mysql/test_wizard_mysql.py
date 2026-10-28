import os

from fastapi.testclient import TestClient

from app import bootstrap, database, prefs
from app.main import app

CFG = {"host": os.environ.get("MYSQL_HOST", "127.0.0.1"), "port": int(os.environ.get("MYSQL_PORT", 3306)),
       "user": "root", "password": os.environ.get("MYSQL_ROOT_PASSWORD", ""), "database": "mynews_wizard"}


def test_full_wizard_flow_on_mysql():
    with TestClient(app) as c:
        assert c.get("/api/setup/status").json()["configured"] is False
        assert c.get("/api/auth/status").status_code == 503

        bad = c.post("/api/setup/test", json={**CFG, "password": "wrong"})
        assert bad.status_code == 400 and "账号或密码错误" in bad.json()["detail"]
        assert "自动创建" in c.post("/api/setup/test", json=CFG).json()["message"]   # 库还不存在

        assert c.post("/api/setup/save", json=CFG).status_code == 200
        assert database.is_mysql() and bootstrap.load_config()["database"] == "mynews_wizard"
        assert c.post("/api/setup/save", json=CFG).status_code == 400              # 配好后向导关闭

        tok = c.post("/api/auth/setup", json={"username": "admin", "password": "secret1"}).json()["token"]
        h = {"Authorization": f"Bearer {tok}"}
        r = c.put("/api/settings/freshrss", headers=h, json={"url": "https://rss.example.com", "username": "me",
                                                             "api_password": "secret-api", "categories": ["科技"]})
        assert r.status_code == 200 and prefs.get("freshrss")["api_password"] == "secret-api"
        assert c.get("/api/overview", headers=h).json()["freshrss"] is True
        assert c.get("/api/issues", headers=h).json() == []
