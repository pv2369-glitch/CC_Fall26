CUISINES = {
    "chinese": "chinese",
    "italian": "italian",
    "japanese": "japanese",
    "mexican": "mexican",
    "indian": "indpak",
    "thai": "thai",
    "korean": "korean",
}

LOCATION = "Manhattan, NY"

MANHATTAN_ZIPS = range(10001, 10283)

TOPUP_LOCATIONS = ["Lower Manhattan, NY", "Midtown Manhattan, NY", "Upper West Side, NY", "Upper East Side, NY"]

TARGET_PER_CUISINE = 200
PAGE_SIZE = 50
MAX_RESULTS = 240

DYNAMO_TABLE = "yelp-restaurants"
OS_INDEX = "restaurants"
OS_TYPE = "Restaurant"

DATA_FILE = "data/restaurants.json"
CACHE_DIR = "data/yelp_cache"