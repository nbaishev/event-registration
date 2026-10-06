from sqlalchemy import Engine, inspect, text
from sqlalchemy.dialects.postgresql import TIMESTAMP, UUID


def test_user_migration_schema_and_constraints(auth_database: Engine) -> None:
    schema = inspect(auth_database)
    assert set(schema.get_table_names()) == {
        "users",
        "events",
        "registrations",
        "alembic_version",
    }
    columns = {c["name"]: c for c in schema.get_columns("users")}
    assert set(columns) == {"id", "email", "password_hash", "created_at", "updated_at"}
    assert all(not c["nullable"] for c in columns.values())
    assert isinstance(columns["id"]["type"], UUID)
    for name in ["created_at", "updated_at"]:
        assert isinstance(columns[name]["type"], TIMESTAMP)
        assert columns[name]["type"].timezone
    assert schema.get_pk_constraint("users")["constrained_columns"] == ["id"]
    assert any(
        c["column_names"] == ["email"] for c in schema.get_unique_constraints("users")
    )
    with auth_database.connect() as connection:
        assert (
            connection.scalar(text("SELECT version_num FROM alembic_version")) == "0003"
        )
