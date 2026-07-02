import logging
import re
import requests
from .base import BaseScraper, Job
from .utils import get_random_ua, random_delay

logger = logging.getLogger(__name__)

REMOTEOK_URL = "https://remoteok.com/api"


class RemoteOKScraper(BaseScraper):
    def scrape(self, keywords: list[str]) -> list[Job]:
        if not self.config.get("sources", {}).get("remoteok", {}).get("enabled", True):
            return []

        jobs: list[Job] = []
        try:
            random_delay()
            resp = requests.get(REMOTEOK_URL, headers={"User-Agent": get_random_ua()}, timeout=(10, 15))
            resp.raise_for_status()
            data = resp.json()
            # first item is a legal notice dict, skip it
            for item in data[1:]:
                if not isinstance(item, dict):
                    continue
                url = item.get("url", "").strip()
                if not url:
                    url = f"https://remoteok.com/remote-jobs/{item.get('id', '')}"
                description = item.get("description", "") or ""
                description = re.sub(r"<[^>]+>", " ", description)
                description = re.sub(r"\s+", " ", description).strip()
                tags = " ".join(item.get("tags", []))
                jobs.append(Job(
                    title=item.get("position", "Unknown"),
                    company=item.get("company", "Unknown"),
                    url=url,
                    description=f"{description}\n\nTags: {tags}",
                    source="remoteok",
                    posted_at=item.get("date", ""),
                ))
        except Exception as e:
            logger.warning("RemoteOK scraper failed: %s", e)

        logger.info("RemoteOK scraped %d jobs", len(jobs))
        return jobs
