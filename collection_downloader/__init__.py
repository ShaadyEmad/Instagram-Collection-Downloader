"""Instagram Collection Downloader.

Collects every post/reel link from one of your saved Instagram collections
with a Selenium-controlled browser and downloads the media with yt-dlp.

The package is split into:

* :mod:`collection_downloader.core` - GUI-independent logic (scraping,
  downloading, cookie handling). Safe to call from worker threads.
* :mod:`collection_downloader.gui`  - the customtkinter desktop interface.
"""

__version__ = "0.3.0"
