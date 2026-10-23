from pathlib import Path

ASX_BASE = "https://www.asx.com.au"

# Network
DOWNLOAD_TIMEOUT = 30       # seconds per PDF download
PAGE_FETCH_TIMEOUT = 60     # seconds for requests page fetch
DOWNLOAD_WORKERS = 6        # parallel download threads

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.0.0 Safari/537.36"
)

# Output
OUTPUT_ROOT = Path("output")
FOLDER_UPDATED  = "Updated_Books"
FOLDER_NO_DATE  = "Date_Not_Found"
DOWNLOAD_CHUNK  = 8_192
