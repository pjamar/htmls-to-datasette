import hashlib
import pathlib
from rich.progress import track
from rich import print
from rich.traceback import install
from datetime import datetime

import click
import html2text
import sqlite_utils

install(show_locals=False)


FILES_TABLE = "files"


class TableColumns(object):
    ID = "id"
    NAME = "name"
    SIZE = "size"
    PATH = "path"
    ADDED = "added"
    PLAINTEXT_CONTENT = "plaintext-content"
    CONTENT = "content"


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
    default="htmlstore.db",
    help="The index database to update.",
)
@click.option(
    "--store-binary",
    "-b",
    is_flag=True,
    default=False,
    help="Insert the file's contents into SQLite DB as binary.",
)
@click.command()
def index(input_dirs: str, database: str, store_binary: bool):
    """Indexes the HTMLs files so they can be searched."""

    print(f"Using database [bold]{database}[/bold].")
    db = sqlite_utils.Database(database)
    initialize_db(db)

    for input_dir in input_dirs:
        search_path = pathlib.Path(input_dir)
        files_to_process = [
            file
            for file in search_path.iterdir()
            if file.is_file() and file.suffix.lower() in [".html", ".htm"]
        ]

        files_indexed = 0
        files_not_indexed = 0
        for file in track(
            files_to_process, description=f'Indexing files on "{search_path}"...'
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
                files_indexed = files_indexed + 1
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
                        TableColumns.ADDED: datetime.now().strftime('%d-%m-%Y'),
                        TableColumns.PLAINTEXT_CONTENT: html2text.html2text(content),
                    }
                    if store_binary:
                        values[TableColumns.CONTENT] = content
                    db["files"].insert(values, pk="id")
            else:
                files_not_indexed = files_not_indexed + 1

        if files_not_indexed:
            print(f"{files_not_indexed} file(s) were already indexed!")
        if files_indexed:
            print(f"{files_indexed} file(s) were indexed.")


@click.option(
    "--database",
    "-d",
    type=click.Path(dir_okay=False),
    default="htmlstore.db",
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
    default="htmlstore.db",
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
        if (not output_path and path.exists()) or (output_path and output_path.joinpath(path.name).exists()):
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
        content = next(db.query(
            f"select {TableColumns.CONTENT} from {FILES_TABLE} where {TableColumns.ID} = :id",
            {"id": row[TableColumns.ID] }
        ))[TableColumns.CONTENT]
        path = output_path.joinpath(pathlib.Path(row[TableColumns.PATH]).name) if output_path else row[TableColumns.PATH]
        with open(path, 'w') as file:
            file.write(content)


@click.group()
def main():
    """Indexes HTML files to allow perform full text search over them."""
    pass


# Add commands and run
def cli():
    main.add_command(index)
    main.add_command(purge)
    main.add_command(extract)
    main()
