FROM python:3.9

RUN mkdir /app
COPY /htmlstore /app
WORKDIR /app

ENV PYTHONPATH=${PYTHONPATH}:${PWD}
RUN pip3 install poetry
RUN poetry config virtualenvs.create false
RUN poetry install --no-dev

VOLUME /app/htmls
VOLUME /app/config

ENTRYPOINT ["datasette", "serve", "htmlstore.db", "--create", "-m", "config/metadata.json", "--plugins-dir=plugins", "-h", "0.0.0.0"]
