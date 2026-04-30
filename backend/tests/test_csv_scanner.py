from app.core.config import Settings
from app.datasources.csv_scanner import CSVScanner


def test_csv_scanner_extracts_one_queryable_table(tmp_path):
    csv_path = tmp_path / "regional_sales.csv"
    csv_path.write_text(
        "Region,Revenue,Revenue\nNorth,10,12\nSouth,20,25\n",
        encoding="utf-8",
    )

    scanner = CSVScanner(Settings())
    scan = scanner.scan("source-123456789", "Regional Sales", csv_path)

    assert scan["checksum"]
    assert len(scan["tables"]) == 1
    table = scan["tables"][0]
    assert table["kind"] == "csv"
    assert table["row_count"] == 2
    assert [column["normalized_name"] for column in table["columns"]] == [
        "region",
        "revenue",
        "revenue_1",
    ]
