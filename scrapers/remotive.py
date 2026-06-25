import logging
import requests
from .base import BaseScraper, Job
from .utils import get_random_ua, random_delay

logger = logging.getLogger(__name__)

REMOTIVE_API = "https://remotive.com/api/remote-jobs"


class RemotiveScraper(BaseScraper):
    def scrape(self, keywords: list[str]) -> list[Job]:
        cfg = self.config.get("sources", {}).get("remotive", {})
        if not cfg.get("enabled", True):
            return []

        categories = cfg.get("categories", ["software-dev", "data"])
        limit = cfg.get("limit_per_category", 50)

        jobs: list[Job] = []
        for i, category in enumerate(categories):
            if i > 0:
                random_delay()
            try:
                resp = requests.get(
                    REMOTIVE_API,
                    params={"category": category, "limit": limit},
                    headers={"User-Agent": get_random_ua()},
                    timeout=15,
                )
                resp.raise_for_status()
                data = resp.json()
                for item in data.get("jobs", []):
                    url = item.get("url", "").strip()
                    if not url:
                        continue
                    tags = ", ".join(item.get("tags", []))
                    description = item.get("description", "") or ""
                    jobs.append(Job(
                        title=item.get("title", "Unknown"),
                        company=item.get("company_name", "Unknown"),
                        url=url,
                        description=f"{description}\n\nTags: {tags}",
                        source="remotive",
                        posted_at=item.get("publication_date", ""),
                    ))
            except Exception as e:
                logger.warning("Remotive category '%s' failed: %s", category, e)

        logger.info("Remotive scraped %d jobs", len(jobs))
        return jobs
