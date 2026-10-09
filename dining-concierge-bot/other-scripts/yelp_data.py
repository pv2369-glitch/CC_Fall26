import hashlib
import json
import os
import time
import urllib.parse
import urllib.request

import config

API_URL = "https://api.yelp.com/v3/businesses/search"
HERE = os.path.dirname(os.path.abspath(__file__))
API_KEY = os.environ["YELP_API_KEY"]

def yelp_search(params):
    key = hashlib.sha1(json.dumps(params, sort_keys=True).encode()).hexdigest()[:16]
    path = os.path.join(HERE, config.CACHE_DIR, f"{key}.json")
    if os.path.exists(path):
        with open(path) as f:
            return json.load(f)

    url = API_URL + "?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers={"Authorization": f"Bearer {API_KEY}"})
    with urllib.request.urlopen(req, timeout=20) as resp:
        data = json.loads(resp.read())

    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        json.dump(data, f)
    time.sleep(0.5)
    return data

def in_manhattan(b):
    zip_code = (b["location"].get("zip_code") or "")[:5]
    return zip_code.isdigit() and int(zip_code) in config.MANHATTAN_ZIPS

def to_record(b, cuisine):
    loc = b["location"]
    coords = b.get("coordinates") or {}
    return {
        "BusinessID": b["id"],
        "Name": b.get("name"),
        "Address": ", ".join(loc.get("display_address") or []),
        "Coordinates": {"Latitude": coords.get("latitude"), "Longitude": coords.get("longitude")},
        "NumberOfReviews": b.get("review_count"),
        "Rating": b.get("rating"),
        "ZipCode": loc.get("zip_code"),
        "Cuisine": cuisine,
    }

def scrape_query(cuisine, alias, location, seen, out):
    added = 0
    for offset in range(0, config.MAX_RESULTS, config.PAGE_SIZE):
        params = {
            "term": f"{cuisine} restaurants",
            "categories": alias,
            "location": location,
            "limit": min(config.PAGE_SIZE, config.MAX_RESULTS - offset),
            "offset": offset,
            "sort_by": "best_match",
        }
        businesses = yelp_search(params)["businesses"]
        for b in businesses:
            if b["id"] not in seen and not b.get("is_closed") and in_manhattan(b):
                seen.add(b["id"])
                out.append(to_record(b, cuisine))
                added += 1
        if len(businesses) < params["limit"]:
            break
    return added

def main():
    seen, records = set(), []
    for cuisine, alias in config.CUISINES.items():
        count = scrape_query(cuisine, alias, config.LOCATION, seen, records)
        for extra_loc in config.TOPUP_LOCATIONS:
            if count >= config.TARGET_PER_CUISINE:
                break
            count += scrape_query(cuisine, alias, extra_loc, seen, records)
        print(f"{cuisine}: {count}")

    with open(os.path.join(HERE, config.DATA_FILE), "w") as f:
        json.dump(records, f, indent=1)
    print(f"Total: {len(records)}")

if __name__ == "__main__":
    main()
