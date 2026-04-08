from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Settings:
    database_dsn: str = os.environ.get(
        'REBUILD3_PG_DSN',
        'postgresql://postgres:123456@192.168.200.217:5433/ip_loc2',
    )
    app_title: str = 'rebuild3 sample workbench'


settings = Settings()
