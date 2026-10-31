import os
import json
import uuid

import pytest
from sqlalchemy import inspect
from sqlalchemy.dialects.mysql import LONGTEXT
from sqlalchemy.exc import DataError

from fastapi.testclient import TestClient

from app import bootstrap, database, prefs
from app.main import app
from app import digest
from app.models import Issue

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


def test_large_digest_and_legacy_content_upgrade():
    name = "mynews_large_" + uuid.uuid4().hex[:12]
    database.connect(bootstrap.build_url({**CFG, "database": name}))
    try:
        data = {"kind": "manual", "window_start": 1, "window_end": 2, "total": 473,
                "sections": [{"category": "科技", "items": [
                    {"title": f"新闻 {i}", "summary": "新闻摘要" * 30} for i in range(473)]}],
                "ai_points": None, "ai_error": None}
        expected = json.dumps({"sections": data["sections"], "highlights": None}, ensure_ascii=False)
        assert len(expected.encode("utf-8")) > 65535
        # Recreate an old deployment; the real save path must reproduce DataError.
        with database.engine.begin() as conn:
            conn.exec_driver_sql("ALTER TABLE `issues` MODIFY COLUMN `content` TEXT NULL")
        with database.session() as db:
            small = digest.save(db, {**data, "total": 0, "sections": []})
            db.commit()
            old_id = small.id
            with pytest.raises(DataError):
                digest.save(db, data)
            db.rollback()
        database.init_db(retries=1)
        database.init_db(retries=1)  # Repeated startup must be safe.
        columns = {c["name"]: c["type"] for c in inspect(database.engine).get_columns("issues")}
        assert isinstance(columns["content"], LONGTEXT)
        with database.session() as db:
            assert json.loads(db.get(Issue, old_id).content) == {"sections": [], "highlights": None}
            large = digest.save(db, data)
            db.commit()
            large_id = large.id
        with database.session() as db:
            assert db.get(Issue, large_id).content == expected
    finally:
        with database.engine.begin() as conn:
            conn.exec_driver_sql(f"DROP DATABASE `{name}`")
        database.reset_engine()
