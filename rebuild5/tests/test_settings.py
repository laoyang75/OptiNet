from pathlib import Path

from rebuild5.backend.app.core.settings import Settings


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def test_settings_defaults_use_rebuild5_paths() -> None:
    settings = Settings()

    assert settings.project_root == PROJECT_ROOT
    assert settings.config_dir == PROJECT_ROOT / "config"
    assert settings.profile_params_path == PROJECT_ROOT / "config" / "profile_params.yaml"
    assert settings.backend_port > 0
    assert settings.frontend_port > 0


def test_settings_supports_dsn_override() -> None:
    settings = Settings(pg_dsn="postgresql://demo:demo@localhost:5432/demo")

    assert settings.pg_dsn == "postgresql://demo:demo@localhost:5432/demo"
