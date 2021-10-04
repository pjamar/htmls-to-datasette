import hashlib
import pathlib
from dataclasses import dataclass
from datetime import datetime

import click
import html2text
import sqlite_utils
from rich import print
from rich.progress import track
from rich.traceback import install

install(show_locals=False)

DATABASE_NAME = "htmlstore.db"
FILES_TABLE = "files"
ACCEPTABLE_HTML_EXTENSIONS = [".html", ".htm"]


@dataclass
class IndexStats:
    already_indexed: int = 0
    indexed: int = 0


class TableColumns(object):
    ID = "id"
    NAME = "name"
    SIZE = "size"
    PATH = "path"
    ADDED = "added"
    PLAINTEXT_CONTENT = "plaintext-content"
    CONTENT = "content"


def index_dir(
    directory: pathlib.Path,
    db: sqlite_utils.Database,
    store_binary: bool,
    recursive: bool,
    stats: IndexStats,
):
    files_to_process = [
        file
        for file in directory.iterdir()
        if file.is_file() and file.suffix.lower() in ACCEPTABLE_HTML_EXTENSIONS
    ]

    for file in track(
        files_to_process, description=f'Indexing files on "{directory}"...'
    ):
        path = str(file)
        previous_file_entry = next(
            db.query(
                f"select id from {FILES_TABLE} where {TableColumns.PATH} = :{TableColumns.PATH}",
                {TableColumns.PATH: path},
            ),
            None,
        )
        if not previous_file_entry:
            stats.indexed = stats.indexed + 1
            filename = file.name
            id_ = hashlib.md5(path.encode("UTF-8")).hexdigest()
            size = file.stat().st_size
            with open(file, "r") as file_handler:
                content = file_handler.read()
                values = {
                    TableColumns.ID: id_,
                    TableColumns.NAME: filename,
                    TableColumns.SIZE: size,
                    TableColumns.PATH: path,
                    TableColumns.ADDED: datetime.now().strftime("%d-%m-%Y"),
                    TableColumns.PLAINTEXT_CONTENT: html2text.html2text(content),
                }
                if store_binary:
                    values[TableColumns.CONTENT] = content
                db[FILES_TABLE].insert(values, pk="id")
        else:
            stats.already_indexed = stats.already_indexed + 1

    if recursive:
        subdirs_to_process = [file for file in directory.iterdir() if file.is_dir()]
        for subdir in subdirs_to_process:
            index_dir(subdir, db, store_binary, recursive, stats)


def html_file_to_text(file):
    with open(file, "r") as file_contents:
        return html2text.html2text(file_contents.read())


def initialize_db(db: sqlite_utils.Database):
    schema = db.schema
    if not schema:
        print(f"Creating database schema...")
        table = db[FILES_TABLE]
        table.create(
            {
                TableColumns.ID: str,
                TableColumns.NAME: str,
                TableColumns.SIZE: int,
                TableColumns.PATH: str,
                TableColumns.ADDED: str,
                TableColumns.PLAINTEXT_CONTENT: str,
                TableColumns.CONTENT: bytes,
            },
            pk="id",
        )
        table.enable_fts(
            ["name", "plaintext-content"], create_triggers=True, tokenize="porter"
        )


@click.argument("input_dirs", type=click.Path(file_okay=False, exists=True), nargs=-1)
@click.option(
    "--database",
    "-d",
    type=click.Path(dir_okay=False),
    default=DATABASE_NAME,
    help="The index database to update.",
)
@click.option(
    "--store-binary",
    "-b",
    is_flag=True,
    default=False,
    help="Insert the file's contents into SQLite DB as binary.",
)
@click.option(
    "--recursive",
    "-r",
    is_flag=True,
    default=False,
    help="Index also files in all subdirectories.",
)
@click.command()
def index(input_dirs: str, database: str, store_binary: bool, recursive: bool):
    """Indexes the HTMLs files so they can be searched."""

    print(f"Using database [bold]{database}[/bold].")
    db = sqlite_utils.Database(database)
    initialize_db(db)

    stats = IndexStats()
    for input_dir in input_dirs:
        index_dir(pathlib.Path(input_dir), db, store_binary, recursive, stats)

    if stats.already_indexed:
        print(f"{stats.already_indexed} file(s) were already indexed!")
    if stats.indexed:
        print(f"{stats.indexed} file(s) were indexed.")


@click.option(
    "--database",
    "-d",
    type=click.Path(dir_okay=False),
    default=DATABASE_NAME,
    help="The index database to update.",
)
@click.option("--dry-run", is_flag=True, help="Do not perform any actions.")
@click.command()
def purge(database: str, dry_run: bool):
    """Removes all files which content is not accessible (on the filesystem or on the database)."""

    print(f"Using database [bold]{database}[/bold].")
    db = sqlite_utils.Database(database)
    initialize_db(db)
    files_table = db[FILES_TABLE]

    missing_files_found = 0
    for row in db.query(f"select id, path from {FILES_TABLE} where content is null"):
        path = pathlib.Path(row[TableColumns.PATH])
        if not path.exists():
            id_ = row[TableColumns.ID]
            missing_files_found = missing_files_found + 1
            if not dry_run:
                print(f"Removing entry [bold]{id_}[/bold] [blue]{path}[/blue]...")
                files_table.delete(id_)
            else:
                print(f"Entry [bold]{id_}[/bold] [blue]{path}[/blue] would be removed.")

    if missing_files_found == 0:
        print("All files were accessible!")
    else:
        print(f"{missing_files_found} file(s) were not accessible!")


@click.option(
    "--output",
    "-o",
    type=click.Path(
        file_okay=False,
        exists=True,
    ),
    help="Specify an output directory. If defined DB entries will be updated if needed with the new location.",
)
@click.option(
    "--database",
    "-d",
    type=click.Path(dir_okay=False),
    default=DATABASE_NAME,
    help="The index database to update.",
)
@click.option("--dry-run", is_flag=True, help="Do not perform any actions.")
@click.command()
def extract(output: str, database: str, dry_run: bool):
    """Extracts all entries whose binary content is stored in the database to files"""

    print(f"Using database [bold]{database}[/bold].")
    db = sqlite_utils.Database(database)
    initialize_db(db)
    files_table = db[FILES_TABLE]
    output_path = pathlib.Path(output) if output else None

    warning_files_found = 0
    files_with_parent_directory_not_found = []
    files_to_extract = []

    missing_files_found = 0
    for row in db.query(
        f"select id, path from {FILES_TABLE} where content is not null"
    ):
        path = pathlib.Path(row[TableColumns.PATH])
        if (not output_path and path.exists()) or (
            output_path and output_path.joinpath(path.name).exists()
        ):
            warning_files_found = warning_files_found + 1
        elif not output_path and not path.parent.exists():
            files_with_parent_directory_not_found.append(row)
        else:
            files_to_extract.append(row)

    if warning_files_found > 0:
        print(
            f"{warning_files_found} Files were [magenta]already found[/magenta] on their destinations."
        )

    parent_directory_not_found = set(
        [
            pathlib.Path(x[TableColumns.PATH]).parent
            for x in files_with_parent_directory_not_found
        ]
    )
    if parent_directory_not_found:
        print(
            f"{len(parent_directory_not_found)} Output directories [magenta]do not exist[/magenta]!"
        )
        for dir in parent_directory_not_found:
            print(f" - {dir}")
        return

    for row in track(files_to_extract, description="Extracting files..."):
        content = next(
            db.query(
                f"select {TableColumns.CONTENT} from {FILES_TABLE} where {TableColumns.ID} = :id",
                {"id": row[TableColumns.ID]},
            )
        )[TableColumns.CONTENT]
        path = (
            output_path.joinpath(pathlib.Path(row[TableColumns.PATH]).name)
            if output_path
            else row[TableColumns.PATH]
        )
        with open(path, "w") as file:
            file.write(content)


@click.argument("query", type=click.STRING, nargs=-1)
@click.option(
    "--database",
    "-d",
    type=click.Path(dir_okay=False),
    default=DATABASE_NAME,
    help="The index database to update.",
)
@click.command()
def search(query: str, database: str):
    """Performs a full text search over the indexed HTML files."""

    print(f"Using database [bold]{database}[/bold].")
    db = sqlite_utils.Database(database)
    initialize_db(db)
    full_query = " ".join(query)

    entries = db.query(
        f"select {TableColumns.ADDED}, {TableColumns.NAME}, {TableColumns.PATH}, {TableColumns.SIZE} "
        + f"from {FILES_TABLE} where rowid in (select rowid from {FILES_TABLE}_fts where {FILES_TABLE}_fts match :q) "
        + f"order by {TableColumns.ADDED} desc "
        + f"limit 50",
        {"q": full_query},
    )

    print(f"Search '{full_query}'")
    for result in entries:
        file = pathlib.Path(result[TableColumns.PATH]).absolute()
        print(f"  - {file}")


@click.group()
def main():
    """Indexes HTML files to allow perform full text search over them."""
    pass


# Add commands and run
def cli():
    main.add_command(index)
    main.add_command(purge)
    main.add_command(extract)
    main.add_command(search)
    main()
