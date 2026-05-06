"""Standalone migration runner — used by Kubernetes pre-upgrade Job."""
import os
import sys

sys.path.insert(0, "/app")

from alembic.config import Config
from alembic import command

from shared.config import settings


def main() -> None:
    service_dir = os.path.dirname(os.path.abspath(__file__))
    cfg = Config()
    cfg.set_main_option("script_location", os.path.join(service_dir, "migrations"))
    cfg.set_main_option("sqlalchemy.url", settings.database_url)
    command.upgrade(cfg, "head")


if __name__ == "__main__":
    main()
