# src/tmdb.py
import os
import json
import threading
from typing import Optional, Tuple, Dict, Any, List

import requests
from concurrent.futures import ThreadPoolExecutor, as_completed

TMDB_BASE = "https://api.themoviedb.org/3"

CACHE_DIR = ".cache"
SEARCH_CACHE_PATH = os.path.join(CACHE_DIR, "search_cache.json")
TITLE_CACHE_DIR = os.path.join(CACHE_DIR, "titles")  # movie_123.json / tv_456.json

_cache_lock = threading.Lock()


def _ensure_cache_dirs():
    os.makedirs(CACHE_DIR, exist_ok=True)
    os.makedirs(TITLE_CACHE_DIR, exist_ok=True)


def headers(read_access_token: str) -> dict:
    return {"Authorization": f"Bearer {read_access_token}", "accept": "application/json"}


def _load_search_cache() -> Dict[str, Any]:
    _ensure_cache_dirs()
    if os.path.exists(SEARCH_CACHE_PATH):
        try:
            with open(SEARCH_CACHE_PATH, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}
    return {}


def _save_search_cache(cache: Dict[str, Any]) -> None:
    _ensure_cache_dirs()
    tmp = SEARCH_CACHE_PATH + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(cache, f, ensure_ascii=False)
    os.replace(tmp, SEARCH_CACHE_PATH)


def _search_cache_key(title: str, year: Optional[int]) -> str:
    # stable string key for json
    return f"{title.strip().lower()}|{year if year is not None else ''}"


def _title_cache_path(media_type: str, tmdb_id: int) -> str:
    _ensure_cache_dirs()
    safe_type = "tv" if media_type == "tv" else "movie"
    return os.path.join(TITLE_CACHE_DIR, f"{safe_type}_{tmdb_id}.json")


def _load_title_from_cache(media_type: str, tmdb_id: int) -> Optional[dict]:
    path = _title_cache_path(media_type, tmdb_id)
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return None
    return None


def _save_title_to_cache(media_type: str, tmdb_id: int, payload: dict) -> None:
    path = _title_cache_path(media_type, tmdb_id)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False)
    os.replace(tmp, path)


def search_multi(read_access_token: str, title: str) -> List[dict]:
    """
    Search across TMDb movie + tv (+ person, but we filter it out).
    """
    params = {"query": title, "include_adult": "false", "language": "en-US", "page": 1}
    r = requests.get(
        f"{TMDB_BASE}/search/multi",
        headers=headers(read_access_token),
        params=params,
        timeout=30,
    )
    r.raise_for_status()
    results = r.json().get("results", [])
    return [x for x in results if x.get("media_type") in ("movie", "tv")]


def _pick_best_result(results: List[dict], year: Optional[int]) -> Tuple[str, int] | None:
    """
    Return (media_type, id) or None.

    Strategy:
      - If year provided, prefer exact year match (release_date / first_air_date).
      - Otherwise take the top result.
    """
    if not results:
        return None

    if year is not None:
        for r in results:
            media_type = r.get("media_type")
            if media_type == "movie":
                d = r.get("release_date") or ""
            else:
                d = r.get("first_air_date") or ""
            if len(d) >= 4 and d[:4].isdigit() and int(d[:4]) == int(year):
                return (media_type, int(r["id"]))

    top = results[0]
    return (top.get("media_type", "movie"), int(top["id"]))


def _normalized_runtime_minutes(payload: dict, media_type: str) -> int:
    """
    Normalize runtime to minutes for widgets.

    Movie: payload['runtime'] (int minutes)
    TV: payload['episode_run_time'] (list[int]) -> pick first positive value
    """
    if media_type == "movie":
        rt = payload.get("runtime")
        return int(rt) if isinstance(rt, int) and rt > 0 else 0

    rts = payload.get("episode_run_time") or []
    if isinstance(rts, list):
        for x in rts:
            if isinstance(x, int) and x > 0:
                return int(x)
    return 0


def title_with_credits(read_access_token: str, media_type: str, tmdb_id: int) -> dict:
    """
    Fetch full payload for movie or tv with credits+keywords appended.
    Cached by (media_type, tmdb_id).
    """
    cached = _load_title_from_cache(media_type, tmdb_id)
    if cached is not None:
        return cached

    params = {"append_to_response": "credits,keywords"}
    r = requests.get(
        f"{TMDB_BASE}/{media_type}/{tmdb_id}",
        headers=headers(read_access_token),
        params=params,
        timeout=30,
    )
    r.raise_for_status()
    payload = r.json()

    # add helpers for downstream widgets
    payload["_media_type"] = media_type
    payload["_normalized_runtime"] = _normalized_runtime_minutes(payload, media_type)

    _save_title_to_cache(media_type, tmdb_id, payload)
    return payload


def resolve_and_fetch_credits_parallel(
    read_access_token: str,
    titles_years: list[tuple[str, int | None]],
    max_workers: int = 12,
):
    """
    For each (title, year), resolve to (media_type, id) using /search/multi,
    then fetch /movie/{id} or /tv/{id} with credits+keywords appended.

    Search cache stores:
      key -> {"media_type": "movie"|"tv"|None, "id": int}
    """
    search_cache = _load_search_cache()
    items: list[dict] = []
    no_match_items: list[dict] = []

    def worker(title: str, year: int | None):
        key = _search_cache_key(title, year)

        with _cache_lock:
            cached = search_cache.get(key)

        if cached is None:
            results = search_multi(read_access_token, title)
            picked = _pick_best_result(results, year)
            if not picked:
                with _cache_lock:
                    search_cache[key] = {"media_type": None, "id": 0}
                return ("NO_MATCH", title, year)

            media_type, tmdb_id = picked
            with _cache_lock:
                search_cache[key] = {"media_type": media_type, "id": int(tmdb_id)}
        else:
            media_type = cached.get("media_type")
            tmdb_id = int(cached.get("id") or 0)

        if not tmdb_id or media_type not in ("movie", "tv"):
            return ("NO_MATCH", title, year)

        payload = title_with_credits(read_access_token, media_type, int(tmdb_id))
        return ("OK", payload)

    with ThreadPoolExecutor(max_workers=max_workers) as ex:
        futures = [ex.submit(worker, t, y) for (t, y) in titles_years]
        for fut in as_completed(futures):
            result = fut.result()
            if result[0] == "OK":
                items.append(result[1])
            else:
                _, title, year = result
                no_match_items.append({"title": title, "year": year})

    _save_search_cache(search_cache)
    return items, no_match_items
