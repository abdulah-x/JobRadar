"""Run once to preview the email template: python test_email.py"""
import yaml
from notifier.email_notifier import EmailNotifier, JobResult

cfg = yaml.safe_load(open("config.yaml", encoding="utf-8"))
email_cfg = cfg["email"]

sample_jobs = [
    JobResult(
        title="ML Engineer — Generative AI",
        company="Arbisoft",
        url="https://example.com/job/1",
        source="linkedin",
        score=92,
        matching_skills=["Python", "PyTorch", "LLM", "RAG", "FastAPI", "Docker", "AWS"],
        missing_skills=["Kubernetes", "Go"],
        reason="Strong alignment with LLM and RAG experience; candidate's project portfolio covers all core requirements.",
        seniority_match=True,
        seniority_level="entry",
        location_ok=True,
        salary_ok=True,
        requires_visa=False,
    ),
    JobResult(
        title="Data Scientist Intern",
        company="Systems Limited",
        url="https://example.com/job/2",
        source="indeed",
        score=81,
        matching_skills=["Python", "Pandas", "Scikit-learn", "SQL", "Jupyter"],
        missing_skills=["R", "SAS"],
        reason="Good match on core DS stack; minor gap in statistical tooling but compensated by strong Python skills.",
        seniority_match=True,
        seniority_level="intern",
        location_ok=True,
        salary_ok=True,
        requires_visa=False,
    ),
]

notifier = EmailNotifier(
    sender=email_cfg["sender"],
    app_password=email_cfg["app_password"],
    recipient=email_cfg["recipient"],
)
notifier.send(sample_jobs)
print("Test email sent!")
