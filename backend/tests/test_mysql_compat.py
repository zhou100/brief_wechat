from sqlalchemy import create_mock_engine, select

from app.models import Base
from app.models.entry import Entry
from app.models.jobs import Job, JobStatus


def test_models_compile_for_mysql_create_all():
    statements = []
    engine = create_mock_engine(
        "mysql+pymysql://",
        lambda sql, *multiparams, **params: statements.append(
            str(sql.compile(dialect=engine.dialect))
        ),
    )

    Base.metadata.create_all(engine)

    ddl = "\n".join(statements).lower()
    assert "uuid" not in ddl
    assert "jsonb" not in ddl
    assert "create type" not in ddl
    assert "entries" in Base.metadata.tables
    assert "jobs" in Base.metadata.tables


def test_available_weeks_query_stays_mysql_safe():
    query = (
        select(Entry.local_date, Entry.created_at)
        .join(Job, Job.entry_id == Entry.id)
        .where(
            Entry.user_id == 1,
            Job.status == JobStatus.DONE,
        )
        .order_by(Entry.local_date.desc(), Entry.created_at.desc())
    )
    engine = create_mock_engine("mysql+pymysql://", lambda *args, **kwargs: None)

    sql = str(query.compile(dialect=engine.dialect)).lower()

    assert "date_trunc" not in sql
    assert "select entries.local_date" in sql
