"""Application settings for rebuild5."""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

import yaml

DEFAULT_DSN = "postgresql://postgres:123456@192.168.200.217:5433/ip_loc2"


@dataclass(slots=True)
class Settings:
    project_root: Path = field(default_factory=lambda: Path(__file__).resolve().parents[3])
    backend_host: str = field(default_factory=lambda: os.getenv("REBUILD5_BACKEND_HOST", "127.0.0.1"))
    backend_port: int = field(default_factory=lambda: int(os.getenv("REBUILD5_BACKEND_PORT", "47231")))
    frontend_host: str = field(default_factory=lambda: os.getenv("REBUILD5_FRONTEND_HOST", "127.0.0.1"))
    frontend_port: int = field(default_factory=lambda: int(os.getenv("REBUILD5_FRONTEND_PORT", "47232")))
    pg_dsn: str = field(default_factory=lambda: os.getenv("REBUILD5_PG_DSN", DEFAULT_DSN))

    @property
    def config_dir(self) -> Path:
        return self.project_root / "config"

    @property
    def profile_params_path(self) -> Path:
        return self.config_dir / "profile_params.yaml"

    @property
    def antitoxin_params_path(self) -> Path:
        return self.config_dir / "antitoxin_params.yaml"

    @property
    def retention_params_path(self) -> Path:
        return self.config_dir / "retention_params.yaml"

    @property
    def dataset_key(self) -> str:
        """Read current dataset_key from config/dataset.yaml."""
        path = self.config_dir / "dataset.yaml"
        if path.exists():
            with path.open("r", encoding="utf-8") as f:
                cfg = yaml.safe_load(f) or {}
            return cfg.get("dataset_key", "beijing_7d")
        return "beijing_7d"


settings = Settings()
