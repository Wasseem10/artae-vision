import logging


def configure_logging(level: str) -> None:
    """Configure concise, structured-enough logs for local and hosted execution."""

    logging.basicConfig(
        level=getattr(logging, level.upper()),
        format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%S%z",
        force=True,
    )
