"""
One-off script: email the last 15 scored jobs that meet the threshold.
Useful to test email delivery with real data already in the DB.
"""
import json
import sqlite3
import sys
import yaml

sys.path.insert(0, "/app")

from notifier.email_notifier import EmailNotifier, JobResult


def main():
    with open("config.yaml") as f:
        config = yaml.safe_load(f)

    email_cfg = config["email"]
    llm_threshold = config["scoring"].get("llm_threshold", 80)

    conn = sqlite3.connect("data/jobs.db")
    conn.row_factory = sqlite3.Row

    # last 15 jobs that were LLM-scored, best scores first
    rows = conn.execute("""
        SELECT title, company, url, source, llm_score,
               matching_skills, missing_skills, reason,
               seniority_match, seniority_level,
               location_ok, salary_ok, requires_visa
        FROM jobs
        WHERE llm_score IS NOT NULL
        ORDER BY seen_at DESC
        LIMIT 15
    """).fetchall()
    conn.close()

    print(f"Last 15 scored jobs (threshold for email: {llm_threshold}):")
    print("-" * 70)

    qualified = []
    for r in rows:
        score = r["llm_score"]
        flag = "✓ QUALIFY" if score >= llm_threshold else "  skip"
        print(f"  [{flag}] {score:>3} | {r['title']} @ {r['company']}")

        if score >= llm_threshold:
            qualified.append(JobResult(
                title=r["title"],
                company=r["company"],
                url=r["url"],
                source=r["source"],
                score=score,
                matching_skills=json.loads(r["matching_skills"] or "[]"),
                missing_skills=json.loads(r["missing_skills"] or "[]"),
                reason=r["reason"] or "",
                seniority_match=bool(r["seniority_match"]),
                seniority_level=r["seniority_level"] or "unknown",
                location_ok=bool(r["location_ok"]),
                salary_ok=bool(r["salary_ok"]) if r["salary_ok"] is not None else True,
                requires_visa=bool(r["requires_visa"]),
            ))

    print("-" * 70)
    print(f"Qualifying jobs: {len(qualified)}")

    if not qualified:
        print("No jobs meet the threshold — nothing to send.")
        return

    print(f"Sending email with {len(qualified)} job(s)...")
    notifier = EmailNotifier(
        sender=email_cfg["sender"],
        app_password=email_cfg["app_password"],
        recipient=email_cfg["recipient"],
    )
    notifier.send(qualified)
    print("Email sent!")


if __name__ == "__main__":
    main()
