import logging
from jobspy import scrape_jobs
from .base import BaseScraper, Job
from .utils import random_delay

logger = logging.getLogger(__name__)


class JobSpyScraper(BaseScraper):
    def scrape(self, keywords: list[str]) -> list[Job]:
        cfg = self.config.get("sources", {}).get("jobspy", {})
        if not cfg.get("enabled", True):
            return []

        sites = cfg.get("sites", ["indeed"])
        results_per_site = cfg.get("results_per_site", 15)
        locations = cfg.get("locations", ["Remote"])
        search_term = " OR ".join(keywords[:4])

        jobs: list[Job] = []
        seen_urls: set[str] = set()

        for i, location in enumerate(locations):
            if i > 0:
                random_delay(2, 4)
            # Use Pakistan for local searches, worldwide for remote
            loc_lower = location.lower()
            if "pakistan" in loc_lower or "lahore" in loc_lower or "islamabad" in loc_lower:
                country = "Pakistan"
            else:
                country = "worldwide"
            try:
                df = scrape_jobs(
                    site_name=sites,
                    search_term=search_term,
                    location=location,
                    results_wanted=results_per_site,
                    country_indeed=country,
                )
                random_delay(1, 3)
                for _, row in df.iterrows():
                    url = str(row.get("job_url", "")).strip()
                    if not url or url in seen_urls:
                        continue
                    seen_urls.add(url)
                    description = str(row.get("description", "") or "")
                    jobs.append(Job(
                        title=str(row.get("title", "Unknown")),
                        company=str(row.get("company", "Unknown")),
                        url=url,
                        description=description,
                        source=str(row.get("site", "jobspy")),
                        posted_at=str(row.get("date_posted", "")),
                    ))
            except Exception as e:
                logger.warning("JobSpy scraper failed for location '%s': %s", location, e)

        logger.info("JobSpy scraped %d jobs across %d locations", len(jobs), len(locations))
        return jobs
