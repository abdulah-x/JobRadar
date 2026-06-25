import logging
import feedparser
import requests
from .base import BaseScraper, Job
from .utils import get_random_ua, random_delay

logger = logging.getLogger(__name__)

REMOTECO_FEEDS = [
    "https://remote.co/remote-jobs/developer/feed/",
    "https://remote.co/remote-jobs/data-science/feed/",
]


class RemoteCoScraper(BaseScraper):
    def scrape(self, keywords: list[str]) -> list[Job]:
        if not self.config.get("sources", {}).get("remoteco", {}).get("enabled", True):
            return []

        jobs: list[Job] = []
        for i, feed_url in enumerate(REMOTECO_FEEDS):
            if i > 0:
                random_delay()
            try:
                resp = requests.get(feed_url, headers={"User-Agent": get_random_ua()}, timeout=15)
                resp.raise_for_status()
                feed = feedparser.parse(resp.content)
                for entry in feed.entries:
                    url = entry.get("link", "").strip()
                    if not url:
                        continue
                    title = entry.get("title", "Unknown")
                    description = entry.get("summary", "") or ""
                    company = entry.get("author", "Unknown")
                    published = entry.get("published", "")
                    jobs.append(Job(
                        title=title,
                        company=company,
                        url=url,
                        description=description,
                        source="remoteco",
                        posted_at=published,
                    ))
            except Exception as e:
                logger.warning("Remote.co feed %s failed: %s", feed_url, e)

        logger.info("Remote.co scraped %d jobs", len(jobs))
        return jobs
