"""Entrypoint: load config, index documents, serve the A2A endpoint."""

import logging
import sys

import uvicorn

from app.a2a_endpoint import build_app
from app.config import ConfigError, load_settings
from app.indexer import Index

log = logging.getLogger("agent")


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    try:
        settings = load_settings()
    except ConfigError as exc:
        print(f"Configuration error: {exc}", file=sys.stderr)
        sys.exit(1)
    index = Index(settings.data_dir)
    log.info("Indexing %s", settings.documents_dir)
    index.sync(settings.documents_dir)
    if index.count() == 0:
        log.warning("No documents found in documents/. Add files and restart.")
    uvicorn.run(build_app(settings, index), host="0.0.0.0", port=8000)


if __name__ == "__main__":
    main()
