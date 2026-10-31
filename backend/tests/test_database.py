from unittest.mock import MagicMock

import pytest
from sqlalchemy import inspect
from sqlalchemy.dialects import mysql, sqlite

from app import database
from app.models import Issue


def test_issue_content_supports_large_mysql_digest():
    # Hundreds of articles exceed MySQL TEXT's 65,535-byte capacity.
    assert Issue.__table__.c.content.type.compile(dialect=mysql.dialect()) == "LONGTEXT"
    assert Issue.__table__.c.content.type.compile(dialect=sqlite.dialect()) == "TEXT"


@pytest.mark.parametrize("existing_type", [mysql.TEXT(), mysql.MEDIUMTEXT(), mysql.LONGTEXT()])
def test_upgrade_existing_issue_content(db, monkeypatch, existing_type):
    inspector = inspect(database.engine)
    real_columns = inspector.get_columns

    def columns(table):
        result = real_columns(table)
        if table == "issues":
            for col in result:
                if col["name"] == "content":
                    col["type"] = existing_type
        return result

    monkeypatch.setattr(inspector, "get_columns", columns)
    monkeypatch.setattr(database, "inspect", lambda engine: inspector)
    engine = MagicMock()
    engine.dialect = mysql.dialect()
    monkeypatch.setattr(database, "engine", engine)
    database.add_missing_columns()
    conn = engine.begin.return_value.__enter__.return_value
    if isinstance(existing_type, mysql.LONGTEXT):
        conn.exec_driver_sql.assert_not_called()
    else:
        conn.exec_driver_sql.assert_called_once_with(
            "ALTER TABLE `issues` MODIFY COLUMN `content` LONGTEXT NULL")
