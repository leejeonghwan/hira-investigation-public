"""HIRA / 공공데이터포털 OpenAPI 호출 클라이언트.

특징
----
- 페이지네이션 자동 반복
- tenacity 기반 지수 백오프 재시도 (429, 5xx, 네트워크 에러)
- XML / JSON 자동 파싱
- 디스크 캐시: 동일 요청은 재요청 안 함 (raw/<endpoint>/<hash>.json)
- **다중 인증키 풀**: 라운드로빈 + 일일 한도 초과 시 자동 폴백
"""
from __future__ import annotations

import hashlib
import json
import logging
import time
from pathlib import Path
from typing import Any, Dict, Iterator, Optional

import requests
import xmltodict
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from ..config import SETTINGS
from .endpoints import Endpoint, get as get_endpoint

logger = logging.getLogger(__name__)


# 데이터포털 일일 한도 초과 에러 메시지·코드
DAILY_LIMIT_TOKENS = (
    "LIMITED_NUMBER_OF_SERVICE_REQUESTS_EXCEEDS",
    "SERVICE_KEY_IS_NOT_REGISTERED_ERROR",
)
DAILY_LIMIT_CODES = ("22", "30")


class HiraAPIError(RuntimeError):
    pass


class DailyLimitReached(HiraAPIError):
    """이 키의 오늘 한도 소진. 풀에서 다음 키로 전환."""


class AllKeysExhausted(HiraAPIError):
    """풀의 모든 키가 오늘 한도 소진."""


class _KeyPool:
    def __init__(self, keys: list[str]) -> None:
        if not keys:
            raise HiraAPIError("no service keys configured. set HIRA_SERVICE_KEY(S) in .env")
        self.keys = list(keys)
        self.exhausted: set[str] = set()
        self.cursor = 0

    def pick(self) -> str:
        for _ in range(len(self.keys)):
            k = self.keys[self.cursor]
            self.cursor = (self.cursor + 1) % len(self.keys)
            if k not in self.exhausted:
                return k
        raise AllKeysExhausted(
            f"all {len(self.keys)} service keys exhausted today. retry tomorrow."
        )

    def mark_exhausted(self, key: str) -> None:
        if key in self.exhausted:
            return
        self.exhausted.add(key)
        logger.warning(
            "key …%s exhausted (%d/%d keys still alive)",
            key[-6:], len(self.keys) - len(self.exhausted), len(self.keys),
        )


class HiraClient:
    def __init__(
        self,
        service_keys: Optional[list[str]] = None,
        base_url: Optional[str] = None,
        page_size: Optional[int] = None,
        cache_dir: Optional[Path] = None,
        timeout: int = 30,
    ) -> None:
        keys = service_keys or list(SETTINGS.service_keys)
        self.pool = _KeyPool(keys)
        self.base_url = (base_url or SETTINGS.base_url).rstrip("/")
        self.page_size = page_size or SETTINGS.page_size
        self.cache_dir = cache_dir or SETTINGS.data_raw
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.timeout = timeout
        self._session = requests.Session()
        logger.info("HiraClient initialized with %d service key(s)", len(self.pool.keys))

    # ------------------------------------------------------------------
    # public API
    # ------------------------------------------------------------------
    def iter_pages(
        self,
        endpoint_name: str,
        params: Dict[str, Any],
        max_pages: Optional[int] = None,
    ) -> Iterator[Dict[str, Any]]:
        endpoint = get_endpoint(endpoint_name)
        page = 1
        while True:
            payload = self._fetch_page(endpoint, params, page)
            items = self._extract_items(payload)
            yield {"page": page, "items": items, "raw": payload}
            total = self._extract_total(payload)
            if not items:
                return
            if total is not None:
                fetched = page * self.page_size
                if fetched >= total:
                    return
            if max_pages and page >= max_pages:
                return
            page += 1
            time.sleep(0.05)

    def collect_all(
        self,
        endpoint_name: str,
        params: Dict[str, Any],
        max_pages: Optional[int] = None,
    ) -> list[Dict[str, Any]]:
        rows: list[Dict[str, Any]] = []
        for page in self.iter_pages(endpoint_name, params, max_pages=max_pages):
            rows.extend(page["items"])
        return rows

    # ------------------------------------------------------------------
    # internals
    # ------------------------------------------------------------------
    @retry(
        reraise=True,
        retry=retry_if_exception_type((requests.RequestException, HiraAPIError)),
        stop=stop_after_attempt(5),
        wait=wait_exponential(multiplier=1, min=2, max=30),
    )
    def _fetch_page(
        self, endpoint: Endpoint, params: Dict[str, Any], page: int
    ) -> Dict[str, Any]:
        # cache 키는 service key 와 무관하게 동일 요청은 동일 응답.
        cache_path = self._cache_path(endpoint, params, page)
        if cache_path.exists():
            return json.loads(cache_path.read_text(encoding="utf-8"))

        # 한도 초과 시 다음 키로 전환하는 내부 루프
        last_err: Exception | None = None
        for _ in range(len(self.pool.keys)):
            key = self.pool.pick()
            try:
                data = self._do_fetch(endpoint, params, page, key)
            except DailyLimitReached:
                self.pool.mark_exhausted(key)
                last_err = DailyLimitReached(f"key …{key[-6:]} exhausted")
                continue
            cache_path.parent.mkdir(parents=True, exist_ok=True)
            cache_path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
            return data
        # 풀 한 바퀴 다 돌았는데도 한도 — 진짜 끝
        raise AllKeysExhausted(str(last_err) if last_err else "no keys available")

    def _do_fetch(
        self, endpoint: Endpoint, params: Dict[str, Any], page: int, key: str
    ) -> Dict[str, Any]:
        key_name = getattr(endpoint, "service_key_param", "ServiceKey")
        full_params = {
            key_name: key,
            endpoint.page_key: page,
            endpoint.rows_key: self.page_size,
            **endpoint.default_params,
            **params,
        }
        missing = [k for k in getattr(endpoint, "required_params", ()) if k not in full_params]
        if missing:
            raise HiraAPIError(f"missing required params for {endpoint.name}: {missing}")

        url = f"{self.base_url}/{endpoint.operation}"
        logger.info("GET %s page=%s key=…%s", endpoint.name, page, key[-6:])
        resp = self._session.get(url, params=full_params, timeout=self.timeout)
        if resp.status_code in (429, 500, 502, 503, 504):
            raise HiraAPIError(f"transient {resp.status_code} from {endpoint.name}")
        resp.raise_for_status()

        text = resp.text
        if endpoint.response_format == "xml":
            data = xmltodict.parse(text)
        else:
            data = resp.json()

        # 공공데이터포털 표준 에러 envelope
        if isinstance(data, dict) and "OpenAPI_ServiceResponse" in data:
            hdr = (data["OpenAPI_ServiceResponse"] or {}).get("cmmMsgHeader", {}) or {}
            msg = str(hdr.get("returnAuthMsg") or "")
            code = str(hdr.get("returnReasonCode") or "")
            if any(tok in msg for tok in DAILY_LIMIT_TOKENS) or code in DAILY_LIMIT_CODES:
                raise DailyLimitReached(f"{code} {msg}")
            raise HiraAPIError(f"OpenAPI error: {hdr}")

        # 일부 API 는 정상 response 안에 errMsg 로 한도 초과를 반환하기도 함
        try:
            hdr = data["response"]["header"]
            msg = str(hdr.get("resultMsg") or "")
            code = str(hdr.get("resultCode") or "")
            if any(tok in msg for tok in DAILY_LIMIT_TOKENS) or code in DAILY_LIMIT_CODES:
                raise DailyLimitReached(f"{code} {msg}")
        except (KeyError, TypeError):
            pass

        return data

    def _cache_path(self, endpoint: Endpoint, params: Dict[str, Any], page: int) -> Path:
        cacheable = {**params, "_page": page}
        digest = hashlib.sha1(
            json.dumps(cacheable, sort_keys=True, ensure_ascii=False).encode("utf-8")
        ).hexdigest()[:16]
        return self.cache_dir / endpoint.name / f"{digest}.json"

    @staticmethod
    def _extract_items(payload: Dict[str, Any]) -> list[Dict[str, Any]]:
        try:
            body = payload["response"]["body"]
        except (KeyError, TypeError):
            return []
        items = body.get("items") if isinstance(body, dict) else None
        if not items:
            return []
        item = items.get("item") if isinstance(items, dict) else items
        if item is None:
            return []
        if isinstance(item, list):
            return item
        return [item]

    @staticmethod
    def _extract_total(payload: Dict[str, Any]) -> Optional[int]:
        try:
            return int(payload["response"]["body"]["totalCount"])
        except (KeyError, TypeError, ValueError):
            return None
