import requests
import yaml
import os
import re
import html
from pathlib import Path
import sqlite3
from datetime import datetime
import json
from zoneinfo import ZoneInfo

## Setting up file paths
PROJECT_DIR = Path(__file__).resolve().parents[2]
JOURNALS_FILE = PROJECT_DIR / "journals.yaml"
DATABASE_FILE = PROJECT_DIR / "papers.db"


## Collecting and saving records


def get_issn(journal: str) -> str:
    """Read journal's ISSN from the project's journal configuration."""
    # Load the journal configuration from the YAML file.
    with JOURNALS_FILE.open(encoding="utf-8") as file:
        config = yaml.safe_load(file)
    # Return the ISSN of the specified journal.
    return config[journal][0]["issn"]


def fetch_records(issn: str, records: int = 100) -> list[dict]:
    """Fetch a specified number of most recently published records for the configured ISSN."""
    # Construct the URL for fetching works from the CrossRef API.
    url = f"https://api.crossref.org/journals/{issn}/works"
    # Set the query parameters for the API request.
    params = {"rows": records, "sort": "published", "order": "desc"}
    # Include the mailto parameter if it is set in the environment.
    mailto = os.getenv("CROSSREF_MAILTO")
    if mailto:
        params["mailto"] = mailto
    # Make the API request to fetch the records.
    response = requests.get(
        url,
        params=params,
        headers={"User-Agent": "econ-newsletter/0.1 (personal research project)"},
        timeout=30,
    )
    # Raise an exception if the request was not successful.
    response.raise_for_status()
    # Return the list of fetched records.
    return response.json()["message"]["items"]


def publication_date(record: dict) -> str | None:
    """Turn Crossref's date-parts value into a simple ISO date."""
    for field in ("published-online", "published-print", "issued"):
        date_parts = record.get(field, {}).get("date-parts", [[]])[0]
        if date_parts:
            return "-".join(
                f"{part:02d}" if index else f"{part:04d}"
                for index, part in enumerate(date_parts)
            )
    return None


def plain_abstract(record: dict) -> str | None:
    """Remove basic markup from the abstract, when Crossref provides one."""
    abstract = record.get("abstract")
    if not abstract:
        return None
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]*>", " ", abstract))).strip()


def save_records(records: list[dict]) -> int:
    """Insert or update records by DOI; keep the original first-seen time."""
    # Get the current timestamp in ISO 8601 format.
    now = datetime.now(ZoneInfo("America/Sao_Paulo")).isoformat(timespec="seconds")
    # Connect to the SQLite database and create the papers table if it doesn't exist.
    saved = 0
    with sqlite3.connect(DATABASE_FILE) as connection:
        connection.execute("""
            CREATE TABLE IF NOT EXISTS papers (
                doi TEXT PRIMARY KEY,
                title TEXT NOT NULL,
                authors TEXT NOT NULL,
                journal TEXT NOT NULL,
                abstract TEXT,
                url TEXT,
                published_at TEXT,
                first_seen_at TEXT NOT NULL,
                source TEXT NOT NULL,
                raw_metadata TEXT NOT NULL,
                is_new INTEGER NOT NULL
            )
            """)

        # Iterate over each record and insert or update it in the database.
        for record in records:
            # Get DOI, title, authors, and journal, skipping the record if DOI is missing.
            doi = record.get("DOI")
            if not doi:
                continue
            title = (record.get("title") or ["Untitled"])[0]
            authors = [
                author.get("name")
                or " ".join(filter(None, [author.get("given"), author.get("family")]))
                for author in record.get("author", [])
            ]
            journal = record.get("container-title")[0]
            # Insert or update the record in the database.
            connection.execute(
                """
                INSERT INTO papers (
                    doi, title, authors, journal, abstract, url, published_at,
                    first_seen_at, source, raw_metadata, is_new
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(doi) DO UPDATE SET
                    title = excluded.title,
                    authors = excluded.authors,
                    journal = excluded.journal,
                    abstract = excluded.abstract,
                    url = excluded.url,
                    published_at = excluded.published_at,
                    source = excluded.source,
                    raw_metadata = excluded.raw_metadata,
                    is_new = 0
                """,
                (
                    doi.lower(),
                    title,
                    json.dumps(authors, ensure_ascii=False),
                    journal,
                    plain_abstract(record),
                    record.get("URL"),
                    publication_date(record),
                    now,
                    "crossref",
                    json.dumps(record, ensure_ascii=False),
                    1,
                ),
            )
            saved += 1
    # Return the number of records successfully saved.
    return saved


def main() -> None:
    journal = "jde"
    issn = get_issn(journal)
    records = fetch_records(issn)
    saved = save_records(records)
    print(
        f"Fetched {len(records)} Crossref records from {journal}; saved {saved} records to {DATABASE_FILE}"
    )


if __name__ == "__main__":
    main()
