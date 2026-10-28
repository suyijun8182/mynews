import os
import sys
import tempfile

_tmp = tempfile.mkdtemp(prefix="mynews-test-")
os.environ["DATABASE_URL"] = f"sqlite:///{_tmp}/test.db"
os.environ["DATA_DIR"] = _tmp
os.environ["TZ"] = "Asia/Shanghai"
os.environ["ADMIN_PASSWORD"] = ""
os.environ["MYNEWS_NO_JOBS"] = "1"   # 不跑定时任务
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import pytest  # noqa: E402

from app import database, notify  # noqa: E402

database.connect(os.environ["DATABASE_URL"])
notify.RETRY_WAIT[:] = [0, 0]   # 重试不等待


@pytest.fixture
def db():
    """每个测试一个干净的库（表结构保留）"""
    from app.models import Article, Delivery, Issue, Setting, User
    s = database.session()
    for m in (Delivery, Issue, Article, User):
        s.query(m).delete()
    s.query(Setting).filter(Setting.key != "secret_key").delete()
    s.commit()
    from app.security import forget_versions
    forget_versions()
    yield s
    s.close()
