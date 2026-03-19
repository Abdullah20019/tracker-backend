from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    app_name: str = "Pakistan Courier Tracking Backend"
    app_env: str = "development"
    backend_shared_secret: str = ""
    cors_allowed_origins: str = "http://localhost:5173,http://127.0.0.1:5173"
    public_api_allowed_origins: str = "http://localhost:5173,http://127.0.0.1:5173"
    trusted_hosts: str = "localhost,127.0.0.1"
    enable_public_docs: bool = False
    enforce_origin_check: bool = True
    cache_ttl_seconds: int = 600
    bulk_limit: int = 20
    request_timeout_seconds: float = 12.0
    max_bulk_concurrency: int = 4
    track_rate_limit_per_minute: int = 60
    bulk_rate_limit_per_minute: int = 12
    health_rate_limit_per_minute: int = 30
    internal_rate_limit_per_minute: int = 30
    max_request_size_bytes: int = 32768
    ca_bundle_path: str = ""
    verify_ssl: bool = True
    lightpanda_command: str = "lightpanda"
    lightpanda_node_script: str = str(Path(__file__).resolve().parents[2] / "lightpanda_runner" / "fetch.mjs")
    lightpanda_wsl_distro: str = "Ubuntu"
    browser_runner_script: str = str(Path(__file__).resolve().parents[2] / "browser_runner" / "fetch.mjs")
    browser_executable_path: str = ""
    edge_driver_path: str = r"C:\edgedriver\msedgedriver.exe"
    allow_edge_fallback: bool = True
    tcs_enabled: bool = True
    pakpost_enabled: bool = True
    daewoo_enabled: bool = True
    leopards_enabled: bool = True
    postex_enabled: bool = True
    mp_enabled: bool = True
    blueex_enabled: bool = True
    callcourier_enabled: bool = False
    trax_enabled: bool = True
    debug_browser_artifacts: bool = False

    model_config = {
        "env_file": ".env",
        "env_file_encoding": "utf-8",
        "extra": "ignore"
    }

    @property
    def cors_allowed_origins_list(self) -> list[str]:
        return [item.strip() for item in self.cors_allowed_origins.split(",") if item.strip()]

    @property
    def public_api_allowed_origins_list(self) -> list[str]:
        values = [item.strip() for item in self.public_api_allowed_origins.split(",") if item.strip()]
        return values or self.cors_allowed_origins_list

    @property
    def trusted_hosts_list(self) -> list[str]:
        return [item.strip() for item in self.trusted_hosts.split(",") if item.strip()]

    @property
    def local_dev_origins(self) -> set[str]:
        return {
            "http://localhost:3000",
            "http://127.0.0.1:3000",
            "http://localhost:3001",
            "http://127.0.0.1:3001",
            "http://localhost:5173",
            "http://127.0.0.1:5173",
            "http://localhost:5174",
            "http://127.0.0.1:5174",
            "http://localhost:5175",
            "http://127.0.0.1:5175",
        }

    @property
    def is_production(self) -> bool:
        return self.app_env.lower() == "production"


@lru_cache
def get_settings() -> Settings:
    return Settings()
