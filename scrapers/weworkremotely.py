import logging
import feedparser
import requests
from .base import BaseScraper, Job
from .utils import get_random_ua, random_delay

logger = logging.getLogger(__name__)

WWR_FEEDS = [
    "https://weworkremotely.com/categories/remote-programming-jobs.rss",
    "https://weworkremotely.com/categories/remote-data-science-jobs.rss",
    "https://weworkremotely.com/categories/remote-devops-sysadmin-jobs.rss",
]


class WeWorkRemotelyScraper(BaseScraper):
    def scrape(self, keywords: list[str]) -> list[Job]:
        if not self.config.get("sources", {}).get("weworkremotely", {}).get("enabled", True):
            return []

        jobs: list[Job] = []
        for i, feed_url in enumerate(WWR_FEEDS):
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
                    title = entry.get("title", "")
                    content_list = entry.get("content") or [{}]
                    description = entry.get("summary", "") or content_list[0].get("value", "")
                    company = entry.get("author", "Unknown")
                    published = entry.get("published", "")
                    jobs.append(Job(
                        title=title,
                        company=company,
                        url=url,
                        description=description,
                        source="weworkremotely",
                        posted_at=published,
                    ))
            except Exception as e:
                logger.warning("WeWorkRemotely feed %s failed: %s", feed_url, e)

        logger.info("WeWorkRemotely scraped %d jobs", len(jobs))
        return jobs
