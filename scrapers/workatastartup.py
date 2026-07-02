import html as _html
import json
import logging
import re
import time

import requests
from bs4 import BeautifulSoup

from .base import BaseScraper, Job
from .utils import get_random_ua, random_delay

logger = logging.getLogger(__name__)

BASE_URL = "https://www.workatastartup.com"

# Listing pages to scrape — Engineering covers ML/Backend/Fullstack, Science covers Research
LISTING_PATHS = [
    "/jobs/l/software-engineer",
    "/jobs/l/science",
]

# roleTypes worth fetching a full description for (may contain ML/AI content)
DETAIL_ROLE_TYPES = {"Machine learning", "Full stack", "Backend", "Research"}

# Title/oneliner keywords that flag a job as likely ML-relevant even if roleType isn't in the set
_ML_TITLE_KEYWORDS = [
    "ai", "ml", "machine learning", "deep learning", "nlp", "llm",
    "data science", "data engineer", "computer vision", "generative",
]


def _fetch_inertia(url: str, session: requests.Session) -> dict:
    r = session.get(url, timeout=(10, 15))
    r.raise_for_status()
    m = re.search(r'data-page="({.*?})"', r.text, re.DOTALL)
    if not m:
        raise ValueError(f"No Inertia data-page found at {url}")
    return json.loads(_html.unescape(m.group(1)))


def _strip_html(html_str: str) -> str:
    if not html_str:
        return ""
    return BeautifulSoup(html_str, "html.parser").get_text(separator=" ", strip=True)


def _is_ml_candidate(job: dict) -> bool:
    if job.get("roleType") in DETAIL_ROLE_TYPES:
        return True
    haystack = (job.get("title", "") + " " + job.get("companyOneLiner", "")).lower()
    return any(kw in haystack for kw in _ML_TITLE_KEYWORDS)


class WorkAtAStartupScraper(BaseScraper):
    def scrape(self, keywords: list[str]) -> list[Job]:
        cfg = self.config.get("sources", {}).get("workatastartup", {})
        if not cfg.get("enabled", True):
            return []

        session = requests.Session()
        session.headers.update({
            "User-Agent": get_random_ua(),
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.5",
        })

        # 1 — collect all listings
        raw: dict[int, dict] = {}  # id → job dict
        for path in LISTING_PATHS:
            try:
                data = _fetch_inertia(BASE_URL + path, session)
                for j in data.get("props", {}).get("jobs", []):
                    raw[j["id"]] = j
            except Exception as e:
                logger.warning("WorkAtAStartup listing %s failed: %s", path, e)

        if not raw:
            logger.warning("WorkAtAStartup scraped 0 jobs (listing fetch failed)")
            return []

        # 2 — fetch detail pages only for ML-candidate jobs
        detail_cache: dict[int, dict] = {}
        candidates = [j for j in raw.values() if _is_ml_candidate(j)]
        for i, listing in enumerate(candidates):
            if i > 0:
                random_delay(1, 2)
            job_id = listing["id"]
            try:
                data = _fetch_inertia(f"{BASE_URL}/jobs/{job_id}", session)
                detail_cache[job_id] = data.get("props", {}).get("job", {})
            except Exception as e:
                logger.debug("WorkAtAStartup detail fetch %s failed: %s", job_id, e)

        # 3 — build Job objects
        jobs: list[Job] = []
        for listing in raw.values():
            job_id = listing["id"]
            detail = detail_cache.get(job_id)

            if detail:
                desc_parts = [_strip_html(detail.get("descriptionHtml", ""))]
                skills = detail.get("skills") or []
                if skills:
                    desc_parts.append("Skills: " + ", ".join(skills))
                description = "\n".join(p for p in desc_parts if p)
            else:
                description = listing.get("companyOneLiner", "")

            salary = listing.get("salary", "") or ""

            jobs.append(Job(
                title=listing.get("title", "Unknown"),
                company=listing.get("companyName", "Unknown"),
                url=f"{BASE_URL}/jobs/{job_id}",
                description=f"{description}\n\nSalary: {salary}".strip(),
                source="workatastartup",
                posted_at=listing.get("companyLastActiveAt", ""),
            ))

        logger.info("WorkAtAStartup scraped %d jobs (%d with full descriptions)", len(jobs), len(detail_cache))
        return jobs
