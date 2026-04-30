from __future__ import annotations

import sqlite3
from pathlib import Path

import pandas as pd


def main() -> None:
    data_dir = Path(".data")
    data_dir.mkdir(exist_ok=True)
    sqlite_path = data_dir / "sample_sales.sqlite"
    excel_path = data_dir / "sample_sales.xlsx"
    csv_path = data_dir / "sample_sales_regions.csv"

    if sqlite_path.exists():
        sqlite_path.unlink()

    conn = sqlite3.connect(sqlite_path)
    try:
        conn.executescript(
            """
            PRAGMA foreign_keys = ON;
            CREATE TABLE customers (
                id INTEGER PRIMARY KEY,
                customer_name TEXT NOT NULL,
                region TEXT NOT NULL
            );
            CREATE TABLE orders (
                id INTEGER PRIMARY KEY,
                customer_id INTEGER NOT NULL,
                order_date TEXT NOT NULL,
                revenue REAL NOT NULL,
                status TEXT NOT NULL,
                FOREIGN KEY(customer_id) REFERENCES customers(id)
            );
            """
        )
        conn.executemany(
            "INSERT INTO customers VALUES (?, ?, ?)",
            [
                (1, "Northwind Components", "North"),
                (2, "Contoso Energy", "South"),
                (3, "Fabrikam Logistics", "West"),
            ],
        )
        conn.executemany(
            "INSERT INTO orders VALUES (?, ?, ?, ?, ?)",
            [
                (1, 1, "2025-01-15", 12500.0, "closed"),
                (2, 1, "2025-02-18", 8700.0, "closed"),
                (3, 2, "2025-02-21", 22200.0, "closed"),
                (4, 3, "2025-03-02", 17100.0, "open"),
                (5, 2, "2025-03-14", 19400.0, "closed"),
            ],
        )
        conn.commit()
    finally:
        conn.close()

    workbook = {
        "Targets": pd.DataFrame(
            [
                {"region": "North", "quarter": "2025-Q1", "target_revenue": 25000},
                {"region": "South", "quarter": "2025-Q1", "target_revenue": 38000},
                {"region": "West", "quarter": "2025-Q1", "target_revenue": 21000},
            ]
        ),
        "Data Quality Notes": pd.DataFrame(
            [
                {"dataset": "orders", "issue": "open orders excluded from closed revenue"},
                {"dataset": "customers", "issue": "region values are standardized"},
            ]
        ),
    }
    with pd.ExcelWriter(excel_path) as writer:
        for sheet, frame in workbook.items():
            frame.to_excel(writer, sheet_name=sheet, index=False)

    pd.DataFrame(
        [
            {"region": "North", "account_owner": "Avery", "risk_score": 0.12},
            {"region": "South", "account_owner": "Morgan", "risk_score": 0.21},
            {"region": "West", "account_owner": "Riley", "risk_score": 0.17},
        ]
    ).to_csv(csv_path, index=False)

    print(f"Created {sqlite_path.resolve()}")
    print(f"Created {excel_path.resolve()}")
    print(f"Created {csv_path.resolve()}")


if __name__ == "__main__":
    main()
