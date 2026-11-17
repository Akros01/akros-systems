#!/usr/bin/env python3
"""Tell IndexNow search engines (Bing, Yandex, Seznam, Naver) that the permit
pages changed. Never fails the build: a refused ping is only logged."""
import json
import os
import sys
import urllib.error
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from config import INDEXNOW_KEY, SITE  # noqa: E402

ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))


def main():
    with open(os.path.join(ROOT, "permits", "data", "urls.json"), encoding="utf-8") as f:
        urls = json.load(f)
    body = {
        "host": "akros01.github.io",
        "key": INDEXNOW_KEY,
        "keyLocation": f"{SITE}/{INDEXNOW_KEY}.txt",
        "urlList": urls,
    }
    req = urllib.request.Request("https://api.indexnow.org/indexnow", data=json.dumps(body).encode("utf-8"),
                                 headers={"Content-Type": "application/json; charset=utf-8"}, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            print(f"IndexNow accepted {len(urls)} URLs (HTTP {resp.status}).")
    except urllib.error.HTTPError as err:
        print(f"IndexNow refused: HTTP {err.code} {err.read()[:300]!r}")
    except Exception as err:
        print(f"IndexNow unreachable: {err!r}")


if __name__ == "__main__":
    main()
