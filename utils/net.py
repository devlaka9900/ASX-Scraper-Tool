"""Shared network state.

INSECURE_SSL flips to True when the page scraper had to retry without SSL
verification (corporate SSL-inspection proxy). The downloader then does the
same, otherwise every PDF download would fail on that network.
"""

INSECURE_SSL = False
