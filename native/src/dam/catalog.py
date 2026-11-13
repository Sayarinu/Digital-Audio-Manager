"""Public song search and exact-result imports; no browser session is needed."""

import re

from . import engine

VIDEO_ID = re.compile(r"[A-Za-z0-9_-]{11}")


def search_music(payload):
    query = str(payload.get("query", "")).strip()
    if not query or len(query) > 300:
        raise engine.WorkerError("Enter a song or artist name, up to 300 characters.")
    try:
        rows = engine.YTMusic().search(query, filter="songs", limit=50)
    except Exception:
        raise engine.WorkerError("Could not search YouTube Music. Check your connection and retry.") from None
    results, seen = [], set()
    for row in rows:
        video_id = row.get("videoId", "")
        if not isinstance(video_id, str) or not VIDEO_ID.fullmatch(video_id) or video_id in seen:
            continue
        seen.add(video_id)
        thumbnails = row.get("thumbnails") or []
        artwork = str(thumbnails[-1].get("url", "")) if thumbnails else ""
        results.append({"id": video_id, "video_id": video_id, "title": str(row.get("title") or "Untitled")[:1000],
                        "artist": engine.artist_from_metadata(row)[:1000],
                        "album": str((row.get("album") or {}).get("name") or "")[:1000],
                        "duration": str(row.get("duration") or ""), "artwork_url": artwork if artwork.startswith("https://") else "",
                        "local_status": "missing", "media_path": None})
    return {"query": query, "results": results}


def queue_search_track(payload):
    track = payload.get("track")
    if not isinstance(track, dict) or not VIDEO_ID.fullmatch(str(track.get("video_id", ""))):
        raise engine.WorkerError("Choose a valid song from the search results.")
    if any(not isinstance(track.get(key, ""), str) or len(track.get(key, "")) > 2000
           for key in ("title", "artist", "album", "duration", "artwork_url")):
        raise engine.WorkerError("That result has invalid song information. Search again.")
    entry = {"videoId": track["video_id"], "title": track.get("title") or "Untitled",
             "artists": [{"name": track.get("artist") or "Unknown artist"}], "duration": track.get("duration"),
             "thumbnails": [{"url": track.get("artwork_url", "")}]
             if track.get("artwork_url", "").startswith("https://") else []}
    con = engine.connect()
    try:
        with con:
            engine.add_unsorted_entries(con, [entry], track.get("album"))
            engine.queue_video_ids(con, [track["video_id"]])
    finally:
        con.close()
    return engine.dashboard()
