import argparse
import hashlib
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

import config

API_URL = "https://api.yelp.com/v3/businesses/search"
HERE = os.path.dirname(os.path.abspath(__file__))
api_calls = 0

def _cache_path(params):
    key = hashlib.sha1(json.dumps(params, sort_keys=True).encode()).hexdigest()[:16]
    return os.path.join(HERE, config.CACHE_DIR, f"{key}.json")

def yelp_search(params, api_key, dry_run=False):
    global api_calls
    path = _cache_path(params)
    if os.path.exists(path):
        with open(path) as f:
            return json.load(f)
    if dry_run:
        print("  [dry-run] would call", params)
        return {"businesses": [], "total": 0}

    url = API_URL + "?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers={"Authorization": f"Bearer {api_key}", "Accept": "application/json"})
    for attempt in range(3):
        try:
            api_calls += 1
            with urllib.request.urlopen(req, timeout=20) as resp:
                data = json.loads(resp.read())
            break
        except urllib.error.HTTPError as e:
            body = e.read().decode(errors="replace")
            if e.code == 429 and attempt < 2:
                time.sleep(2 ** attempt * 2)
                continue
            sys.exit(f"Yelp API error {e.code}: {body}")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        json.dump(data, f)
    time.sleep(0.5)
    return data

def to_record(b, cuisine):
    loc = b.get("location") or {}
    coords = b.get("coordinates") or {}
    return {
        "BusinessID": b["id"],
        "Name": b.get("name"),
        "Address": ", ".join(loc.get("display_address") or []) or loc.get("address1"),
        "Coordinates": {"Latitude": coords.get("latitude"), "Longitude": coords.get("longitude")},
        "NumberOfReviews": b.get("review_count"),
        "Rating": b.get("rating"),
        "ZipCode": loc.get("zip_code"),
        "Cuisine": cuisine,
        "Phone": b.get("display_phone"),
        "Price": b.get("price"),
        "Categories": [c.get("title") for c in b.get("categories") or []],
        "Url": (b.get("url") or "").split("?")[0],
    }

def scrape_query(cuisine, alias, location, seen, out, api_key, dry_run):
    added = 0
    offset = 0
    while offset < config.MAX_RESULTS:
        limit = min(config.PAGE_SIZE, config.MAX_RESULTS - offset)
        params = {
            "term": f"{cuisine} restaurants",
            "categories": alias,
            "location": location,
            "limit": limit,
            "offset": offset,
            "sort_by": "best_match",
        }
        data = yelp_search(params, api_key, dry_run)
        businesses = data.get("businesses") or []
        for b in businesses:
            if b.get("id") and b["id"] not in seen and not b.get("is_closed"):
                seen.add(b["id"])
                out.append(to_record(b, cuisine))
                added += 1
        total = data.get("total", 0)
        offset += limit
        if len(businesses) < limit or offset >= total:
            break
    return added

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    api_key = os.environ.get("YELP_API_KEY")
    if not api_key and not args.dry_run:
        sys.exit("Set YELP_API_KEY first (export YELP_API_KEY=...)")

    seen, records = set(), []
    for cuisine, alias in config.CUISINES.items():
        count = scrape_query(cuisine, alias, config.LOCATION, seen, records, api_key, args.dry_run)
        for extra_loc in config.TOPUP_LOCATIONS:
            if count >= config.TARGET_PER_CUISINE:
                break
            count += scrape_query(cuisine, alias, extra_loc, seen, records, api_key, args.dry_run)
        print(f"{cuisine:>10}: {count} unique restaurants")

    if args.dry_run:
        print("\n[dry-run] nothing written")
        return

    out_path = os.path.join(HERE, config.DATA_FILE)
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, "w") as f:
        json.dump(records, f, indent=1)
    print(f"\nTotal unique restaurants: {len(records)} -> {out_path}")
    print(f"Yelp API calls made this run: {api_calls}")
    if len(records) < 1000:
        print("WARNING: fewer than 1,000 restaurants - add a cuisine to config.CUISINES and re-run (cached calls are free).")

if __name__ == "__main__":
    main()
