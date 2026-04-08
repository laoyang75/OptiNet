from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    database_url: str = "postgresql+asyncpg://postgres:123456@192.168.200.217:5433/ip_loc2"
    database_url_sync: str = "postgresql://postgres:123456@192.168.200.217:5433/ip_loc2"
    app_title: str = "望优数据治理工作台"
    debug: bool = True
    statement_timeout_ms: int = 30000
    pool_size: int = 10
    max_overflow: int = 10
    pool_timeout: int = 30

    class Config:
        env_file = ".env"


settings = Settings()
