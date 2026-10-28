"""我的新闻 单文件二进制的入口：PyInstaller 打包用，也可直接 python 运行做本地冒烟。

Linux 一键安装用轻量数据库：没有 DATABASE_URL 时默认用 SQLite（数据目录下 mynews.db），安装向导跳过 MySQL 这一步。
想用 MySQL 的话在 /etc/mynews.env 里设 DATABASE_URL。
"""
import os


def main():
    # 冻结后的数据文件在 sys._MEIPASS；前端 dist 由 spec 打包到 _MEIPASS/frontend_dist，
    # main.py 的默认 FRONTEND_DIR（__file__/../frontend_dist）恰好解析到这里
    data_dir = os.path.abspath(os.environ.get("DATA_DIR") or os.path.join(os.getcwd(), "data"))
    os.environ["DATA_DIR"] = data_dir
    os.makedirs(data_dir, exist_ok=True)
    if not os.environ.get("DATABASE_URL") and not os.path.exists(os.path.join(data_dir, "db_config.json")):
        os.environ["DATABASE_URL"] = f"sqlite:///{os.path.join(data_dir, 'mynews.db')}"
    port = int(os.environ.get("HTTP_PORT") or 8844)
    import uvicorn
    uvicorn.run("app.main:app", host=os.environ.get("HOST", "0.0.0.0"), port=port,
                access_log=False, log_level=os.environ.get("LOG_LEVEL", "info"))


if __name__ == "__main__":
    main()
