import hashlib
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from zoneinfo import ZoneInfo

_PKT = ZoneInfo("Asia/Karachi")


@dataclass
class Job:
    title: str
    company: str
    url: str
    description: str
    source: str
    posted_at: str = field(default_factory=lambda: datetime.now(_PKT).isoformat())
    id: str = field(init=False)

    def __post_init__(self):
        normalized = self.url.strip().lower().rstrip("/")
        self.id = hashlib.sha256(normalized.encode()).hexdigest()[:16]
        if len(self.description) > 4000:
            self.description = self.description[:4000]


def passes_keyword_filter(job: Job, keywords: list[str], exclude: list[str]) -> bool:
    full_text = f"{job.title} {job.description}".lower()
    title_text = job.title.lower()
    has_keyword = any(kw.lower() in full_text for kw in keywords)
    # exclude only on title — descriptions routinely mention senior/years in context
    has_exclude = any(ex.lower() in title_text for ex in exclude)
    return has_keyword and not has_exclude


class BaseScraper(ABC):
    def __init__(self, config: dict):
        self.config = config

    @abstractmethod
    def scrape(self, keywords: list[str]) -> list[Job]:
        pass
