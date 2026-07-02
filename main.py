import logging
import sys
from pathlib import Path

import yaml
from apscheduler.schedulers.blocking import BlockingScheduler

from ai.github_processor import GitHubProcessor
from ai.job_scorer import JobScorer
from ai.resume_processor import ResumeProcessor
from ai.semantic_filter import SemanticFilter
from notifier.email_notifier import EmailNotifier, JobResult
from scrapers.base import passes_keyword_filter
from scrapers.jobspy_scraper import JobSpyScraper
from scrapers.weworkremotely import WeWorkRemotelyScraper
from scrapers.remoteok import RemoteOKScraper
from scrapers.remoteco import RemoteCoScraper
from scrapers.remotive import RemotiveScraper
from scrapers.workatastartup import WorkAtAStartupScraper
from scrapers.utils import random_delay
from store.job_store import JobStore

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    stream=sys.stdout,
)
logger = logging.getLogger("main")


def load_config(path: str = "config.yaml") -> dict:
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def run_pipeline(
    config: dict,
    store: JobStore,
    resume_processor: ResumeProcessor,
    gh_processor: "GitHubProcessor | None" = None,
    include_jobspy: bool = True,
) -> None:
    stats = store.stats()
    logger.info(
        "=== Pipeline run starting === (DB: %d seen, %d notified, %.2f MB)",
        stats["total_seen"], stats["total_notified"], stats["db_size_mb"],
    )

    filters = config.get("filters", {})
    keywords = filters.get("keywords", [])
    exclude_keywords = filters.get("exclude_keywords", [])
    scoring_cfg = config.get("scoring", {})
    semantic_threshold = scoring_cfg.get("semantic_threshold", 0.45)
    llm_threshold = scoring_cfg.get("llm_threshold", 80)
    daily_limit = scoring_cfg.get("daily_job_limit", 20)
    email_cfg = config.get("email", {})

    # rebuild resume index if resume.txt changed
    if resume_processor.needs_rebuild():
        logger.info("Resume changed — rebuilding index...")
        resume_processor.build()

    # refresh GitHub index if repos changed
    if gh_processor and gh_processor.needs_rebuild():
        logger.info("GitHub repos changed — rebuilding GitHub index...")
        gh_processor.build(resume_processor.get_collection())

    profile = resume_processor.load_profile()
    semantic_filter = SemanticFilter(resume_processor, threshold=semantic_threshold)
    scorer = JobScorer(
        resume_processor,
        profile,
        groq_api_key=scoring_cfg.get("groq_api_key", ""),
        groq_model=scoring_cfg.get("groq_model", "llama-3.3-70b-versatile"),
        gemini_model=scoring_cfg.get("gemini_model", "gemini-2.5-flash"),
    )

    scrapers = [
        *([ JobSpyScraper(config) ] if include_jobspy else []),
        WeWorkRemotelyScraper(config),
        RemoteOKScraper(config),
        RemoteCoScraper(config),
        RemotiveScraper(config),
        WorkAtAStartupScraper(config),
    ]

    all_jobs = []
    for i, scraper in enumerate(scrapers):
        if i > 0:
            random_delay(1, 2)
        try:
            jobs = scraper.scrape(keywords)
            all_jobs.extend(jobs)
        except Exception as e:
            logger.warning("Scraper %s crashed: %s", type(scraper).__name__, e)

    source_counts: dict[str, int] = {}
    for job in all_jobs:
        source_counts[job.source] = source_counts.get(job.source, 0) + 1
    logger.info("Total scraped: %d jobs | by source: %s", len(all_jobs), source_counts)

    # dedup across sources by id (same url → same id)
    seen_ids: set[str] = set()
    unique_jobs = []
    for job in all_jobs:
        if job.id not in seen_ids:
            seen_ids.add(job.id)
            unique_jobs.append(job)

    logger.info("After cross-source dedup: %d unique jobs", len(unique_jobs))

    # filter out already-seen jobs (single batch query instead of N individual lookups)
    already_seen = store.seen_ids([j.id for j in unique_jobs])
    new_jobs = [j for j in unique_jobs if j.id not in already_seen]
    logger.info("New (unseen) jobs: %d", len(new_jobs))

    # keyword pre-filter
    keyword_filtered = []
    keyword_rejected = []
    for j in new_jobs:
        if passes_keyword_filter(j, keywords, exclude_keywords):
            keyword_filtered.append(j)
        else:
            keyword_rejected.append(j)

    # save rejected jobs to DB so they don't reappear as "new" on the next run
    for j in keyword_rejected:
        store.save_filtered(j, 0.0)

    if keyword_rejected:
        sample_titles = [j.title for j in keyword_rejected[:8]]
        logger.info("Keyword-rejected sample (%d total): %s", len(keyword_rejected), sample_titles)

    logger.info("After keyword filter: %d jobs", len(keyword_filtered))

    filter_cfg = filters
    seniority_allowed = filter_cfg.get("seniority_allowed", ["entry", "associate", "intern", "unknown"])

    qualified: list[JobResult] = []

    for job in keyword_filtered:
        # Stage 1: semantic similarity
        if job.description.strip():
            passes, sim_score = semantic_filter.passes(job.description)
        else:
            passes, sim_score = True, 0.0  # no description — let LLM decide

        if not passes:
            logger.debug("Stage 1 filtered: %s @ %s (sim=%.3f)", job.title, job.company, sim_score)
            store.save_filtered(job, sim_score)
            continue

        logger.info("Stage 1 passed: %s @ %s (sim=%.3f) — scoring...", job.title, job.company, sim_score)

        result = scorer.score(job.title, job.company, job.description)

        # If scoring completely failed, skip saving so it's retried next run
        if result.reason == "Scoring failed":
            logger.warning("  Scoring failed for '%s' @ %s — will retry next run", job.title, job.company)
            continue

        # Seniority gate — discard mid/senior without storing score data
        if result.seniority_level not in seniority_allowed:
            logger.info(
                "  Seniority discard: %s @ %s — level=%s",
                job.title, job.company, result.seniority_level,
            )
            store.save_filtered(job, sim_score)
            continue

        # Other hard gates (location / salary / visa)
        hard_fail_reasons = []
        if not result.location_ok:
            hard_fail_reasons.append("location not Lahore/Islamabad/valid-remote")
        if not result.salary_ok:
            hard_fail_reasons.append("salary below threshold")
        if result.requires_visa:
            hard_fail_reasons.append("requires visa/work authorization")

        if hard_fail_reasons:
            logger.info(
                "  Hard-filtered: %s @ %s — %s",
                job.title, job.company, ", ".join(hard_fail_reasons),
            )
            store.save_scored(job, sim_score, result, notified=False)
            continue

        store.save_scored(job, sim_score, result, notified=False)
        logger.info("  Score: %d | seniority=%s | %s", result.score, result.seniority_level, result.reason)

        if result.score >= llm_threshold:
            qualified.append((job.id, JobResult(
                title=job.title,
                company=job.company,
                url=job.url,
                source=job.source,
                score=result.score,
                matching_skills=result.matching_skills,
                missing_skills=result.missing_skills,
                reason=result.reason,
                seniority_match=result.seniority_match,
                seniority_level=result.seniority_level,
                location_ok=result.location_ok,
                salary_ok=result.salary_ok,
                requires_visa=result.requires_visa,
                posted_at=job.posted_at or "",
            )))

    logger.info("Qualified jobs (≥%d): %d", llm_threshold, len(qualified))

    if qualified:
        qualified.sort(key=lambda x: x[1].score, reverse=True)

        sent_today = store.notified_today()
        remaining = daily_limit - sent_today
        logger.info("Daily quota: %d/%d used, %d remaining", sent_today, daily_limit, remaining)

        if remaining <= 0:
            logger.info("Daily quota reached — %d qualifying jobs held back", len(qualified))
        else:
            to_send = qualified[:remaining]
            job_ids = [jid for jid, _ in to_send]
            results = [jr for _, jr in to_send]

            notifier = EmailNotifier(
                api_key=email_cfg["resend_api_key"],
                sender=email_cfg["sender"],
                recipient=email_cfg["recipient"],
            )
            if notifier.send(results, sent_before=sent_today, daily_limit=daily_limit):
                store.mark_notified(job_ids)

            held_back = len(qualified) - len(to_send)
            if held_back:
                logger.info("%d jobs scored above threshold but held back by daily quota", held_back)
    else:
        logger.info("No qualifying jobs this run — no email sent")

    stats = store.stats()
    logger.info(
        "DB stats: %d total seen, %d total notified, %.2f MB | by source: %s",
        stats["total_seen"], stats["total_notified"], stats["db_size_mb"], stats["by_source"],
    )
    logger.info("=== Pipeline run complete ===")


def main() -> None:
    config = load_config()
    data_dir = "data"
    Path(data_dir).mkdir(exist_ok=True)

    gemini_key = config["scoring"]["gemini_api_key"]
    if not gemini_key or not gemini_key.strip() or gemini_key == "YOUR_GEMINI_API_KEY":
        logger.error("GEMINI_API_KEY is missing or not set — cannot start.")
        sys.exit(1)

    email_cfg = config.get("email", {})
    for field in ("sender", "resend_api_key", "recipient"):
        if not email_cfg.get(field, "").strip():
            logger.error("Email config missing '%s' — set it before running.", field)
            sys.exit(1)

    store = JobStore(data_dir)
    gemini_model = config.get("scoring", {}).get("gemini_model", "gemini-2.5-flash")
    resume_processor = ResumeProcessor("resume.txt", data_dir, gemini_key, gemini_model=gemini_model)

    # build resume index on first run
    if resume_processor.needs_rebuild():
        logger.info("First run — building resume index...")
        resume_processor.build()

    # build GitHub index on first run (or if repos changed)
    gh_processor = None
    github_cfg = config.get("github", {})
    if github_cfg.get("username"):
        gh_processor = GitHubProcessor(
            username=github_cfg["username"],
            data_dir=data_dir,
            gemini_api_key=gemini_key,
            token=github_cfg.get("token") or None,
            max_repos=github_cfg.get("max_repos", 20),
            include_readme=github_cfg.get("include_readme", True),
        )
        if gh_processor.needs_rebuild():
            logger.info("Building GitHub project index for '%s'...", github_cfg["username"])
            gh_processor.build(resume_processor.get_collection())
        else:
            logger.info("GitHub index is up to date.")

    schedule_cfg = config.get("schedule", {})
    remote_minutes = schedule_cfg.get("remote_minutes", 30)
    jobspy_hours = schedule_cfg.get("jobspy_hours", 3)
    logger.info(
        "Scheduler starting — remote boards every %d min, JobSpy every %d hrs",
        remote_minutes, jobspy_hours,
    )

    import datetime
    from zoneinfo import ZoneInfo
    PKT = ZoneInfo("Asia/Karachi")
    scheduler = BlockingScheduler(timezone="Asia/Karachi")

    # Remote-only job (WeWorkRemotely, RemoteOK, Remote.co, Remotive)
    scheduler.add_job(
        run_pipeline,
        trigger="interval",
        minutes=remote_minutes,
        args=[config, store, resume_processor, gh_processor, False],
        id="pipeline_remote",
        next_run_time=datetime.datetime.now(PKT),
    )

    # JobSpy job (LinkedIn, Indeed, Glassdoor, ZipRecruiter)
    # Staggered 5 minutes after the remote job to avoid concurrent Gemini scoring
    scheduler.add_job(
        run_pipeline,
        trigger="interval",
        hours=jobspy_hours,
        args=[config, store, resume_processor, gh_processor, True],
        id="pipeline_jobspy",
        next_run_time=datetime.datetime.now(PKT) + datetime.timedelta(minutes=5),
    )

    try:
        scheduler.start()
    except (KeyboardInterrupt, SystemExit):
        logger.info("Scheduler stopped.")


if __name__ == "__main__":
    main()
