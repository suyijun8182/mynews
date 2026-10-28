from sqlalchemy import BigInteger, Column, Index, Integer, String, Text

from app.database import Base


class User(Base):
    """单用户：只有一个管理员账号（表结构留着 id，以后要加账号不用改表）"""
    __tablename__ = "users"
    id = Column(Integer, primary_key=True, autoincrement=True)
    username = Column(String(64), unique=True, nullable=False)
    password_hash = Column(String(255), nullable=False)
    token_version = Column(Integer, default=0)   # 改密码后 +1，旧登录令牌立即失效
    created = Column(BigInteger)
    last_login = Column(BigInteger)


class Setting(Base):
    """网页上改的配置（JSON），见 app.prefs；敏感字段加密后再存"""
    __tablename__ = "settings"
    key = Column(String(64), primary_key=True)
    value = Column(Text)


class Article(Base):
    """从 FreshRSS 拉来的文章缓存。first_issue 记录它第一次进了哪一期，用来避免重复推送"""
    __tablename__ = "articles"
    id = Column(String(64), primary_key=True)            # FreshRSS 条目 ID（长格式里的 16 位十六进制）
    title = Column(String(500), nullable=False)
    url = Column(String(1000))
    source = Column(String(255))                         # 订阅源名称
    category = Column(String(255))                       # FreshRSS 分类（label）
    summary = Column(String(500))                        # 正文去掉 HTML 后的开头一段
    crawled = Column(BigInteger, nullable=False)         # 进入 FreshRSS 的时间（秒）：早晚报按它划时间窗口
    published = Column(BigInteger)
    first_issue = Column(Integer)
    __table_args__ = (Index("ix_articles_crawled", "crawled"), Index("ix_articles_issue", "first_issue"))


class Issue(Base):
    """一期早报 / 晚报 / 手动推送"""
    __tablename__ = "issues"
    id = Column(Integer, primary_key=True, autoincrement=True)
    kind = Column(String(16), nullable=False)            # morning | evening | manual
    window_start = Column(BigInteger, nullable=False)
    window_end = Column(BigInteger, nullable=False)
    created = Column(BigInteger, nullable=False)
    total = Column(Integer, default=0)                   # 本期文章总数（不截断）
    content = Column(Text)                               # JSON：{sections: [{category, items: [...]}]}
    ai_points = Column(Text)                             # JSON：[{text, refs: [文章序号]}]；没开 AI 时为空
    ai_error = Column(String(500))
    token = Column(String(32))                           # 「查看全部」只读链接的令牌
    status = Column(String(16), default="pending")       # pending | sent | partial | failed | empty
    __table_args__ = (Index("ix_issues_created", "created"),)


class Delivery(Base):
    """每期每个渠道的推送结果"""
    __tablename__ = "deliveries"
    id = Column(Integer, primary_key=True, autoincrement=True)
    issue_id = Column(Integer, nullable=False)
    channel = Column(String(32), nullable=False)
    ok = Column(Integer, default=0)
    error = Column(String(500))
    attempts = Column(Integer, default=0)
    parts = Column(Integer, default=0)                   # 消息拆成了几条
    ts = Column(BigInteger)
    __table_args__ = (Index("ix_deliveries_issue", "issue_id"),)
