#!/usr/bin/env python3
"""Sync Bangumi anime collections into a standalone data repository.

The generated files are served by GitHub Pages:
  data.json
  covers/<subject_id>.webp

Token is read from BGM_TOKEN or the local .bgm_token file. Never commit it.
"""
import colorsys
import io
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

from PIL import Image, ImageOps, features

ROOT = Path(__file__).resolve().parent
TOKEN_FILE = ROOT / ".bgm_token"
DATA_FILE = ROOT / "data.json"
COVER_DIR = ROOT / "covers"
API = "https://api.bgm.tv"
USER_AGENT = "akabane-bgm-data/1.0"
STATUS = {1: "想看", 2: "看过", 3: "在看"}

# 只在追番页展示正篇，隐藏 OAD、剧场版、番外和衍生作。
HIDDEN_SUBJECT_IDS = {
    268726,  # 关于我转生变成史莱姆这档事 OAD
    299673,  # 转生史莱姆日记
    350185,  # 剧场版 红莲之绊篇
    421174,  # 柯里乌斯之梦
    515595,  # 剧场版 苍海之泪篇
    302523,  # 第二季 第2部分
    616596,  # 第四季 第3部分
}

COVER_SIZE = (480, 480)


def get_token():
    token = os.environ.get("BGM_TOKEN", "").strip()
    if not token and TOKEN_FILE.exists():
        token = TOKEN_FILE.read_text(encoding="utf-8").strip()
    if not token:
        raise SystemExit("missing BGM_TOKEN or .bgm_token")
    return token


def headers(token):
    return {
        "Authorization": "Bearer " + token,
        "User-Agent": USER_AGENT,
        "Accept": "application/json",
    }


def api_json(url, token, attempts=3):
    last_error = None
    for attempt in range(attempts):
        req = urllib.request.Request(url, headers=headers(token))
        try:
            with urllib.request.urlopen(req, timeout=30) as response:
                return json.load(response)
        except urllib.error.HTTPError as error:
            last_error = error
            if error.code in (429, 500, 502, 503, 504) and attempt < attempts - 1:
                time.sleep(2 * (attempt + 1))
                continue
            detail = error.read().decode("utf-8", "replace")[:300]
            raise SystemExit("BGM API %s: %s" % (error.code, detail))
        except urllib.error.URLError as error:
            last_error = error
            if attempt < attempts - 1:
                time.sleep(2 * (attempt + 1))
                continue
            raise SystemExit("BGM API network error: %s" % error)
    raise SystemExit("BGM API failed: %s" % last_error)


def fetch_collections(username, token):
    items = []
    for status_type in (3, 1, 2):
        offset = 0
        while True:
            query = urllib.parse.urlencode({
                "subject_type": 2,
                "type": status_type,
                "limit": 50,
                "offset": offset,
            })
            data = api_json("%s/v0/users/%s/collections?%s" % (API, username, query), token)
            page = data.get("data") or []
            for row in page:
                subject = row.get("subject") or {}
                if not subject or subject.get("id") in HIDDEN_SUBJECT_IDS:
                    continue
                images = subject.get("images") or {}
                image_url = (
                    images.get("large")
                    or images.get("common")
                    or images.get("medium")
                    or images.get("small")
                )
                items.append({
                    "id": subject.get("id"),
                    "title": subject.get("name_cn") or subject.get("name") or "",
                    "original": subject.get("name") or "",
                    "status": STATUS.get(row.get("type"), ""),
                    "type": row.get("type"),
                    "ep_status": row.get("ep_status") or 0,
                    "eps": subject.get("eps") or 0,
                    "score": subject.get("score") or None,
                    "date": subject.get("date") or "",
                    "cover": "",
                    "color": "",
                    "url": "https://bgm.tv/subject/%s" % subject.get("id"),
                    "updated_at": row.get("updated_at") or "",
                    "_image_url": image_url or "",
                })
            offset += len(page)
            if not page or offset >= (data.get("total") or 0):
                break
            time.sleep(0.2)
    return items


def linear_channel(value):
    value = value / 255.0
    if value <= 0.04045:
        return value / 12.92
    return ((value + 0.055) / 1.055) ** 2.4


def luminance(rgb):
    return (
        0.2126 * linear_channel(rgb[0])
        + 0.7152 * linear_channel(rgb[1])
        + 0.0722 * linear_channel(rgb[2])
    )


def dominant_color(image):
    small = image.resize((64, 64), Image.LANCZOS)
    quantized = small.quantize(colors=8)
    palette = quantized.getpalette() or []
    counts = quantized.getcolors() or []
    if not counts:
        return "#29b6f6"

    total = sum(row[0] for row in counts)
    candidates = []
    for count, index in counts:
        base = index * 3
        if base + 3 > len(palette):
            continue
        rgb = tuple(palette[base:base + 3])
        if not (0.18 <= luminance(rgb) <= 0.78):
            continue
        if count < total * 0.03:
            continue
        hue, saturation, value = colorsys.rgb_to_hsv(*(channel / 255.0 for channel in rgb))
        candidates.append((saturation, count, hue, value))
    if not candidates:
        return "#29b6f6"

    # 选封面里有代表性、饱和度最高的中间调，再抬高饱和度让 4px 进度条更清楚。
    best = max(candidates, key=lambda row: (row[0], row[1]))
    _, _, hue, value = best
    saturation = max(best[0], 0.55)
    rgb = colorsys.hsv_to_rgb(hue, saturation, value)
    return "#%02x%02x%02x" % tuple(int(round(channel * 255)) for channel in rgb)


def download_cover(item, token):
    image_url = item.get("_image_url")
    if not image_url:
        return
    req = urllib.request.Request(image_url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=40) as response:
        raw = response.read()
    image = Image.open(io.BytesIO(raw)).convert("RGB")
    cover = ImageOps.fit(image, COVER_SIZE, method=Image.LANCZOS, centering=(0.5, 0.5))
    item["color"] = dominant_color(cover)

    COVER_DIR.mkdir(parents=True, exist_ok=True)
    target = COVER_DIR / ("%s.webp" % item["id"])
    temp = COVER_DIR / ("%s.tmp" % item["id"])
    cover.save(temp, format="WEBP", quality=82, method=6)
    temp.replace(target)
    item["cover"] = "covers/%s.webp" % item["id"]


def write_json(items, user):
    for item in items:
        item.pop("_image_url", None)
    temp = DATA_FILE.with_name(DATA_FILE.name + ".tmp")
    temp.write_text(
        json.dumps({"user": user, "items": items}, ensure_ascii=False, indent=1) + "\n",
        encoding="utf-8",
    )
    temp.replace(DATA_FILE)


def remove_orphan_covers(items):
    expected = {"%s.webp" % item["id"] for item in items if item.get("cover")}
    for path in COVER_DIR.glob("*.webp"):
        if path.name not in expected:
            path.unlink()


def main():
    if not features.check("webp"):
        raise SystemExit("Pillow lacks WebP support")

    token = get_token()
    me = api_json(API + "/v0/me", token)
    username = os.environ.get("BGM_USERNAME", "").strip() or str(
        me.get("username") or me.get("id")
    )
    items = fetch_collections(username, token)

    for item in items:
        try:
            download_cover(item, token)
        except Exception as error:
            existing = COVER_DIR / ("%s.webp" % item["id"])
            if existing.exists():
                item["cover"] = "covers/%s.webp" % item["id"]
            print("cover failed for %s: %s" % (item["id"], error), file=sys.stderr)
        time.sleep(0.2)

    order = {"在看": 0, "想看": 1, "看过": 2}
    items.sort(key=lambda item: (order.get(item["status"], 9), item.get("updated_at") or ""))

    write_json(items, {
        "id": me.get("id"),
        "username": me.get("username"),
        "nickname": me.get("nickname"),
    })
    remove_orphan_covers(items)

    counts = {}
    for item in items:
        counts[item["status"]] = counts.get(item["status"], 0) + 1
    print("saved %s items to %s" % (len(items), DATA_FILE))
    print("status:", counts)
    print("covers:", len(list(COVER_DIR.glob("*.webp"))))


if __name__ == "__main__":
    main()
