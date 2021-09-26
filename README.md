# htmls-to-datasette

Htmls-to-datasette is a tool to index HTML files into a [Sqlite](https://sqlite.org) database so they can be searched and
visualized at a later time. This can be useful for web archival/web clipping purposes.

The database created is designed to be served on [Datasette](https://datasette.io/) and to allow to read the indexed
files through it. 

This tool was created to serve my own work flow that is:
 1. Have a browser with [SingleFile](https://github.com/gildas-lormeau/SingleFile) extension installed.
 2. When there is an interesting blog post or article save a full web page into one HTML using SingleFile.
 3. The created `.html` file on the downloads folder is moved to a common repository (via cron job).
 4. This common repository is synched to my main server (I use [Syncthing](https://syncthing.net/) for this).
 5. On my personal server all the new HTML files are moved to the serving folder and this indexer is called to populate
    the search database.
 6. Datasette with an specific configuration will allow searching on these files and reading them online.

The indexing tool can insert the HTML contents on the database itself, to be served from there, or not. In this second
case the files will be served from the location they were indexed from. 

## Setup

This project uses *[Poetry](https://python-poetry.org/)* to make it easier to setup the appropriate dependencies to run.

Installation steps for *Poetry* can be checked on their [website](https://python-poetry.org/docs/#installation) but for
most of the cases this command line would work:
```bash
curl -sSL https://raw.githubusercontent.com/python-poetry/poetry/master/get-poetry.py | python -
```
*Note that you should exercise caution when running something directly from Internet.*  

### Install dependencies:
```bash
poetry install
```

### Build

```bash
poetry build
```

### Install

I use [pipx](https://pypa.github.io/pipx) for installing packages on isolated environments. You can install this package
from the `dist/` directory in whichever way you prefer or you can 
[install pipx](https://pypa.github.io/pipx/installation/).  

The installation with pipx would be:
```bash
pipx install dist/htmls-to-datasette-0.1.0.tar.gz
```

## Usage

`htmls-to-datasette index [OPTIONS] [INPUT_DIRS]...` will create a database named `htmlstore.db' (by default).

### Example

Get into the server directory:
```bash
cd server
```

Because this example requires Datasette to run you would have to get them using poetry:
```bash
poetry init
```

Now index the example file using `htmls-to-datasette`:
```bash
htmls-to-datasette index input
```

All files contained in `input` (`.html` and `.html`) will be indexed and a full text search index created. Whenever
there are new files to be indexed this command can be run in the same way.

And now run the Datasette server:
```bash
poetry run datasette serve htmlstore.db -m metadata-files.json --plugins-dir=plugins
```

You'll see the address to send your browser to on the screen. There is also a shortcut to make it easier to perform a
full text search. Should be reachable at http://127.0.0.1:8001/htmlstore/search just fill the query on the 'q' parameter
and you will search over the indexed HTMLs. Click on the HTML file name will load its contents.

For this to work the server will require the files to be on their location (relative in this case). So if the `input`
folder is moved away or not accesible the files would be searchable but the contents will not be available.

There is an additional example that stores these files onto the Sqlite database itself. This has its advantages as
everything needed for serving and searching the content will be contained in one file.

```bash
# You should be on the server directory
rm htmlstore.db   # Remove the previous example's database
htmls-to-datasette index input --store-binary  # Index files and store its contents

# Now run Datasette, note that now we need to use a different metadata as the contents needed to be served
# in a different way (from the DB itself). 
poetry run datasette serve htmlstore.db -m metadata-binary.json --plugins-dir=plugins
```

### TODO

- Clear content when extracting files.
- Better documentation.
