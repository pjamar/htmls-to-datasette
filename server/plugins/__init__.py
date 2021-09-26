from datasette import hookimpl
from markupsafe import Markup

HTMLSAFE_TAG = "||HTMLSAFE||"
HTMLSAFE_TAG_LENGTH = len(HTMLSAFE_TAG)


def link_html_file(key, name=None):
    if not name:
        name = key
    return f"{HTMLSAFE_TAG}<a href='/-/media/html/{key}'>{name}</a>"


def render_as_html_if_tagged(value):
    if not isinstance(value, str):
        return None
    if value.startswith(HTMLSAFE_TAG):
        return Markup(value[HTMLSAFE_TAG_LENGTH:])
    else:
        return value


@hookimpl
def prepare_connection(conn):
    conn.create_function("link_html_file", 2, link_html_file)


@hookimpl
def render_cell(value, column, table, database, datasette):
    if column in ["plaintext-content", "content"]:
        return value[:150] + "..." if value else ""
    else:
        return render_as_html_if_tagged(value)
