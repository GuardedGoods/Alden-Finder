"""Tiny robots.txt cache. Respects Disallow rules for our User-Agent."""

from __future__ import annotations

import logging
from urllib.parse import urlparse
from urllib.robotparser import RobotFileParser

import httpx

log = logging.getLogger(__name__)

_CACHE: dict[str, RobotFileParser] = {}


async def _load(root: str, client: httpx.AsyncClient) -> RobotFileParser:
    rp = RobotFileParser()
    url = f"{root}/robots.txt"
    try:
        r = await client.get(url, timeout=10)
        rp.parse(r.text.splitlines() if r.status_code == 200 else [])
    except httpx.HTTPError as e:
        log.debug("robots.txt unreadable for %s: %s", root, e)
        rp.parse([])
    return rp


async def allowed(url: str, user_agent: str, client: httpx.AsyncClient) -> bool:
    p = urlparse(url)
    root = f"{p.scheme}://{p.netloc}"
    rp = _CACHE.get(root)
    if rp is None:
        rp = await _load(root, client)
        _CACHE[root] = rp
    return rp.can_fetch(user_agent, url)
