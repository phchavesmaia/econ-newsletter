import json
import sqlite3
import webbrowser
from pathlib import Path
import subprocess
import sys
from textual.app import App, ComposeResult
from textual.containers import Horizontal, VerticalScroll
from textual.widgets import DataTable, Footer, Header, Static

## Setting up file paths and database connection
PROJECT_DIR = Path(__file__).resolve().parents[2]
DATABASE_FILE = PROJECT_DIR / "papers.db"

## Creating the TUI


def load_papers() -> list[dict]:
    """Read papers from the collector's SQLite database."""
    # If the database does not exist, run the collector to create it.
    if not DATABASE_FILE.exists():
        print(f"Database not found at {DATABASE_FILE}. Collecting papers...")
        subprocess.run(
            [sys.executable, PROJECT_DIR / "src" / "econ_newsletter" / "collector.py"],
            check=True,
        )
    # Connect to the database in read-only mode.
    database_uri = f"{DATABASE_FILE.as_uri()}?mode=ro"
    with sqlite3.connect(database_uri, uri=True) as connection:
        # Set the row factory to return rows as dictionaries.
        connection.row_factory = sqlite3.Row
        # Execute the query to fetch the papers, ordered by newness and publication date.
        rows = connection.execute("""
            SELECT doi, title, authors, journal, abstract, url, published_at, is_new
            FROM papers
            ORDER BY is_new DESC, published_at IS NULL, published_at DESC, first_seen_at DESC
            """).fetchall()
    # Convert the fetched rows to a list of dictionaries and return them.
    return [dict(row) for row in rows]


class NewsletterApp(App[None]):
    """Browse collected papers in the terminal."""

    # Application title, subtitle, key bindings, and CSS styling.
    TITLE = "Econ Newsletter"
    SUB_TITLE = "Recent papers"
    BINDINGS = [
        ("o", "open_paper", "Open paper"),
        ("q", "quit", "Quit"),
    ]
    CSS = """
    #main {
        height: 1fr;
    }

    #papers {
        width: 3fr;
        height: 1fr;
    }

    #detail-pane {
        width: 2fr;
        height: 1fr;
        border: round $accent;
        padding: 1 2;
    }
    """

    # Initialize the application state.
    def __init__(self) -> None:
        super().__init__()
        self.papers_by_doi: dict[str, dict] = {}
        self.selected_paper: dict | None = None

    # Compose the layout of the application.
    def compose(self) -> ComposeResult:
        yield Header()
        with Horizontal(id="main"):
            yield DataTable(id="papers", cursor_type="row")
            with VerticalScroll(id="detail-pane"):
                yield Static("Loading papers…", id="details", markup=False)
        yield Footer()

    # Handle the event when the application is mounted.
    def on_mount(self) -> None:
        # Constructing table columns
        table = self.query_one("#papers", DataTable)
        table.add_column("New", width=4)
        table.add_column("Date", width=12)
        table.add_column("Journal", width=33)
        table.add_column("Title", width=60)

        # Loading papers from the database and populating the table.
        papers = load_papers()
        for paper in papers:
            doi = paper["doi"]
            self.papers_by_doi[doi] = paper
            table.add_row(
                "Yes" if paper["is_new"] else "No",
                paper["published_at"] or "Unknown",
                paper["journal"],
                paper["title"],
                key=doi,
            )

        # Move the cursor to the first row of the table.
        table.move_cursor(row=0)

    # Handle the event when a row in the data table is highlighted.
    def on_data_table_row_highlighted(self, event: DataTable.RowHighlighted) -> None:
        if event.row_key is None:
            return

        # Identifying selected paper based on the highlighted row.
        doi = str(event.row_key.value)
        self.selected_paper = self.papers_by_doi[doi]
        paper = self.selected_paper

        # Populating the detail pane with the selected paper's information.
        authors = ", ".join(json.loads(paper["authors"])) or "Unknown"
        abstract = paper["abstract"] or "No abstract is available."
        details = (
            f"{paper['title']}\n\n"
            f"{paper['journal']} · {paper['published_at'] or 'Date unknown'}\n"
            f"Authors: {authors}\n\n"
            f"{abstract}\n\n"
            f"DOI: {paper['doi']}"
        )

        # Updating the detail pane with the constructed details string.
        self.query_one("#details", Static).update(details)

    def action_open_paper(self) -> None:
        if not self.selected_paper or not self.selected_paper["url"]:
            self.notify("This paper has no URL in the database.")
            return
        # Open the URL of the selected paper in the default web browser.
        webbrowser.open(self.selected_paper["url"])


def main() -> None:
    NewsletterApp().run()


if __name__ == "__main__":
    main()
