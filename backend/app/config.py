"""运行配置：来自环境变量（见 .env.example）。

FreshRSS、早晚报、推送渠道、AI 摘要这些都在网页上配置，存在数据库 settings 表里，见 app.prefs。
"""
from functools import lru_cache
from zoneinfo import ZoneInfo

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # Docker 部署留空：首次打开网页时在安装向导里填写 MySQL 信息，保存到 data/db_config.json
    # Linux 一键安装由启动器默认设成 SQLite（数据目录下 mynews.db）
    # 也可以直接指定：mysql+pymysql://user:pass@host:3306/mynews?charset=utf8mb4 或 sqlite:///./mynews.db
    database_url: str = ""

    http_port: int = 8844
    tz: str = "Asia/Shanghai"

    # JWT 签名和敏感字段加密用的密钥；留空则首次启动随机生成并保存到数据库
    secret_key: str = ""
    # 首次启动的管理员密码；留空则由安装向导设置
    admin_password: str = ""

    @property
    def zone(self) -> ZoneInfo:
        return ZoneInfo(self.tz)


@lru_cache
def get_settings() -> Settings:
    return Settings()
