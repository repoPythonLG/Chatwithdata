import sqlite3

from app.core.config import Settings
from app.datasources.sqlite_scanner import SQLiteScanner


def test_sqlite_scanner_extracts_tables_columns_and_declared_relationships(tmp_path):
    db_path = tmp_path / "sales.sqlite"
    conn = sqlite3.connect(db_path)
    try:
        conn.executescript(
            """
            PRAGMA foreign_keys = ON;
            CREATE TABLE customers (
                id INTEGER PRIMARY KEY,
                name TEXT NOT NULL
            );
            CREATE TABLE orders (
                id INTEGER PRIMARY KEY,
                customer_id INTEGER NOT NULL,
                amount REAL,
                FOREIGN KEY(customer_id) REFERENCES customers(id)
            );
            INSERT INTO customers VALUES (1, 'Acme');
            INSERT INTO orders VALUES (1, 1, 12.5);
            """
        )
        conn.commit()
    finally:
        conn.close()

    scanner = SQLiteScanner(Settings())
    scan = scanner.scan("source-123456789", "Sales", db_path)

    assert scan["checksum"]
    assert {table["original_name"] for table in scan["tables"]} == {"customers", "orders"}
    assert any(rel["evidence"] == "Declared SQLite foreign key" for rel in scan["relationships"])
