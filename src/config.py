"""환경설정 로더.

.env 또는 OS 환경변수에서 HIRA OpenAPI 호출에 필요한 값을 읽어온다.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / ".env", override=False)


@dataclass(frozen=True)
class Settings:
    service_keys: tuple[str, ...]
    base_url: str
    page_size: int
    concurrency: int
    data_raw: Path
    data_processed: Path
    data_reference: Path
    reports_tables: Path
    reports_figures: Path

    @property
    def service_key(self) -> str:
        """첫 번째 키 — 하위호환용. 신규 코드는 service_keys 사용."""
        return self.service_keys[0] if self.service_keys else ""


def load_settings() -> Settings:
    # HIRA_SERVICE_KEYS (콤마 구분) 가 우선, 없으면 HIRA_SERVICE_KEY 단일값.
    raw = os.getenv("HIRA_SERVICE_KEYS") or os.getenv("HIRA_SERVICE_KEY", "")
    keys = tuple(k.strip() for k in raw.split(",") if k.strip())
    return Settings(
        service_keys=keys,
        base_url=os.getenv("HIRA_BASE_URL", "https://apis.data.go.kr/B551182"),
        page_size=int(os.getenv("HIRA_PAGE_SIZE", "1000")),
        concurrency=int(os.getenv("HIRA_CONCURRENCY", "2")),
        data_raw=ROOT / "data" / "raw",
        data_processed=ROOT / "data" / "processed",
        data_reference=ROOT / "data" / "reference",
        reports_tables=ROOT / "reports" / "tables",
        reports_figures=ROOT / "reports" / "figures",
    )


SETTINGS = load_settings()
