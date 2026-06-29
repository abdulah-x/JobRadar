import logging
import time
from dataclasses import dataclass
from datetime import datetime

logger = logging.getLogger(__name__)

FONT = "'Times New Roman', Times, serif"

# Dark theme palette — warm navy-slate (Catppuccin Mocha inspired)
BG_PAGE    = "#1e1e2e"   # deep warm navy — not pure black
BG_CARD    = "#313244"   # elevated surface — readable card bg
BG_CARD2   = "#282839"   # inner section — subtly deeper than card
BORDER     = "#45475a"   # muted slate border
DIVIDER    = "#383850"   # soft divider
TEXT_PRI   = "#cdd6f4"   # lavender white — easy on the eyes
TEXT_SEC   = "#a6adc8"   # medium contrast secondary
TEXT_MUTED = "#6c7086"   # muted labels


@dataclass
class JobResult:
    title: str
    company: str
    url: str
    source: str
    score: int
    matching_skills: list[str]
    missing_skills: list[str]
    reason: str
    seniority_match: bool
    seniority_level: str = "unknown"
    location_ok: bool = True
    salary_ok: bool = True
    requires_visa: bool = False


def _score_color(score: int) -> str:
    if score >= 90: return "#4ade80"
    if score >= 80: return "#60a5fa"
    if score >= 60: return "#fb923c"
    return "#f87171"


def _score_bg(score: int) -> str:
    if score >= 90: return "#0d2818"
    if score >= 80: return "#0c1a40"
    if score >= 60: return "#2a1500"
    return "#2d0a0a"


_SENIORITY = {
    "entry":     ("#4ade80", "#0d2818"),
    "associate": ("#60a5fa", "#0c1a40"),
    "intern":    ("#c084fc", "#1e0a3c"),
    "mid":       ("#fb923c", "#2a1500"),
    "senior":    ("#f87171", "#2d0a0a"),
    "unknown":   ("#9ca3af", "#1c1c24"),
}


def _pill(text: str, fg: str, bg: str, bold: bool = False) -> str:
    weight = "600" if bold else "500"
    return (
        f'<span style="display:inline-block;padding:4px 11px;margin:2px 4px 2px 0;'
        f'border-radius:999px;font-size:12px;font-weight:{weight};line-height:1.4;'
        f'font-family:{FONT};background:{bg};color:{fg};white-space:nowrap;">{text}</span>'
    )


def _job_card(index: int, job: JobResult) -> str:
    sc = _score_color(job.score)
    sb = _score_bg(job.score)

    fg, bg = _SENIORITY.get(job.seniority_level, _SENIORITY["unknown"])
    seniority_pill = _pill(job.seniority_level.capitalize(), fg, bg, bold=True)

    matching_pills = "".join(
        _pill(f"&#10003;&nbsp;{s}", "#4ade80", "#0d2818") for s in job.matching_skills
    ) if job.matching_skills else f'<span style="color:{TEXT_MUTED};font-size:13px;font-family:{FONT};">—</span>'

    missing_pills = "".join(
        _pill(f"&times;&nbsp;{s}", "#f87171", "#2d0a0a") for s in job.missing_skills
    ) if job.missing_skills else f'<span style="color:{TEXT_MUTED};font-size:13px;font-family:{FONT};">None</span>'

    loc_text  = "Remote / PK" if job.location_ok else "Location mismatch"
    loc_fg    = "#4ade80" if job.location_ok else "#f87171"
    loc_bg    = "#0d2818" if job.location_ok else "#2d0a0a"

    sal_text  = "Salary OK" if job.salary_ok else "Below threshold"
    sal_fg    = "#4ade80" if job.salary_ok else "#fb923c"
    sal_bg    = "#0d2818" if job.salary_ok else "#2a1500"

    visa_pill = _pill("Visa required", "#f87171", "#2d0a0a") if job.requires_visa else ""

    src = job.source.replace("-", " ").title()
    company = (
        job.company if job.company and job.company.lower() not in ("nan", "none", "")
        else "Company undisclosed"
    )

    return f"""
<div style="background:{BG_CARD};border:1px solid {BORDER};border-radius:12px;margin-bottom:20px;overflow:hidden;">

  <!-- Title row -->
  <table style="width:100%;border-collapse:collapse;"><tr>
    <td style="padding:20px 16px 16px 20px;vertical-align:top;">
      <div style="font-size:11px;font-weight:600;color:{TEXT_MUTED};letter-spacing:0.09em;text-transform:uppercase;margin-bottom:6px;font-family:{FONT};">
        #{index} &nbsp;&middot;&nbsp; {src}
      </div>
      <div style="font-size:18px;font-weight:700;color:{TEXT_PRI};line-height:1.3;font-family:{FONT};margin-bottom:3px;">{job.title}</div>
      <div style="font-size:13px;color:{TEXT_MUTED};font-family:{FONT};">{company}</div>
    </td>
    <td style="vertical-align:middle;padding:20px 20px 16px 8px;text-align:right;width:80px;">
      <div style="display:inline-block;background:{sb};border-radius:50%;width:56px;height:56px;">
        <table style="width:56px;height:56px;border-collapse:collapse;"><tr><td style="text-align:center;vertical-align:middle;padding:0;">
          <div style="font-size:20px;font-weight:800;color:{sc};line-height:1;font-family:{FONT};">{job.score}</div>
          <div style="font-size:9px;color:{sc};opacity:0.75;font-weight:600;font-family:{FONT};">/100</div>
        </td></tr></table>
      </div>
    </td>
  </tr></table>

  <!-- Reason -->
  <div style="padding:0 20px 16px 20px;">
    <p style="margin:0;font-size:14px;font-weight:400;color:{TEXT_SEC};line-height:1.65;font-family:{FONT};font-style:italic;">
      &ldquo;{job.reason}&rdquo;
    </p>
  </div>

  <!-- Divider -->
  <div style="height:1px;background:{DIVIDER};"></div>

  <!-- Skills Match -->
  <div style="padding:18px 20px 16px 20px;background:{BG_CARD2};">
    <div style="font-size:11px;font-weight:700;color:{TEXT_SEC};letter-spacing:0.09em;text-transform:uppercase;margin-bottom:16px;font-family:{FONT};">
      Skills Match
    </div>

    <div style="margin-bottom:16px;">
      <div style="font-size:11px;font-weight:600;color:#4ade80;margin-bottom:7px;font-family:{FONT};">Matching</div>
      <div style="line-height:2.2;">{matching_pills}</div>
    </div>

    <div>
      <div style="font-size:11px;font-weight:600;color:#f87171;margin-bottom:7px;font-family:{FONT};">To Develop</div>
      <div style="line-height:2.2;">{missing_pills}</div>
    </div>
  </div>

  <!-- Divider -->
  <div style="height:1px;background:{DIVIDER};"></div>

  <!-- Footer meta -->
  <div style="padding:13px 20px 15px 20px;background:{BG_CARD};">
    <table style="width:100%;border-collapse:collapse;"><tr>
      <td style="vertical-align:middle;padding:0;">
        <span style="font-size:10px;font-weight:700;color:{TEXT_MUTED};text-transform:uppercase;letter-spacing:0.07em;margin-right:6px;font-family:{FONT};">Level</span>
        {seniority_pill}
        {_pill(loc_text, loc_fg, loc_bg)}
        {_pill(sal_text, sal_fg, sal_bg)}
        {visa_pill}
      </td>
      <td style="vertical-align:middle;padding:0 0 0 14px;text-align:right;white-space:nowrap;">
        <a href="{job.url}" target="_blank" rel="noopener noreferrer"
           style="display:inline-block;padding:8px 22px;background:#1d4ed8;color:#e0e7ff;
           border-radius:7px;text-decoration:none;font-size:13px;font-weight:600;
           font-family:{FONT};letter-spacing:0.02em;">
          Apply &nbsp;&#8594;
        </a>
      </td>
    </tr></table>
  </div>

</div>"""


def _build_html(jobs: list[JobResult], sent_before: int = 0, daily_limit: int = 20) -> str:
    cards = "\n".join(_job_card(i + 1, j) for i, j in enumerate(jobs))
    from zoneinfo import ZoneInfo
    date_str = datetime.now(ZoneInfo("Asia/Karachi")).strftime("%B %d, %Y &nbsp;&middot;&nbsp; %H:%M PKT")
    count = len(jobs)
    sent_after = sent_before + count
    label = f"{count} new role{'s' if count != 1 else ''} matched your profile"
    quota_label = f"{sent_after}&thinsp;/&thinsp;{daily_limit} sent today"

    return f"""<!DOCTYPE html>
<html lang="en">
<head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1.0"></head>
<body style="margin:0;padding:0;background:{BG_PAGE};">
<div style="max-width:640px;margin:0 auto;padding:24px 16px 40px;">

  <!-- Header -->
  <div style="background:linear-gradient(135deg,#1e1e3a 0%,#2a2a6e 55%,#24244a 100%);border:1px solid #45475a;border-radius:14px;padding:26px 24px;margin-bottom:22px;">
    <table style="width:100%;border-collapse:collapse;"><tr>
      <td style="vertical-align:middle;padding:0;">
        <div style="font-size:11px;font-weight:700;letter-spacing:0.16em;text-transform:uppercase;color:rgba(148,163,184,0.7);margin-bottom:8px;font-family:{FONT};">
          Job Radar &nbsp;&middot;&nbsp; <span style="color:rgba(96,165,250,0.85);">{quota_label}</span>
        </div>
        <h1 style="margin:0 0 9px;font-size:22px;font-weight:800;color:#e2e8f0;line-height:1.25;font-family:{FONT};">{label}</h1>
        <p style="margin:0;font-size:13px;font-weight:500;color:rgba(226,232,240,0.78);font-family:{FONT};">{date_str}</p>
      </td>
      <td style="vertical-align:middle;padding:0 0 0 20px;text-align:center;width:72px;">
        <div style="background:rgba(255,255,255,0.08);border:1px solid rgba(255,255,255,0.12);border-radius:10px;padding:11px 14px;">
          <div style="font-size:28px;font-weight:800;color:#e2e8f0;line-height:1;font-family:{FONT};">{count}</div>
          <div style="font-size:10px;font-weight:600;color:rgba(226,232,240,0.6);text-transform:uppercase;letter-spacing:0.06em;margin-top:2px;font-family:{FONT};">{"job" if count == 1 else "jobs"}</div>
        </div>
      </td>
    </tr></table>
  </div>

  <!-- Cards -->
  {cards}

  <!-- Footer -->
  <p style="text-align:center;font-size:11px;color:{TEXT_MUTED};margin:10px 0 0;font-family:{FONT};">
    Job Radar &nbsp;&middot;&nbsp; Entry / Associate / Intern &nbsp;&middot;&nbsp; Lahore, Islamabad, or Remote
  </p>

</div>
</body>
</html>"""


class EmailNotifier:
    def __init__(self, api_key: str, sender: str, recipient: str):
        self.api_key = api_key
        self.sender = sender
        self.recipient = recipient

    def send(self, jobs: list[JobResult], sent_before: int = 0, daily_limit: int = 20) -> bool:
        if not jobs:
            return False

        import resend
        resend.api_key = self.api_key

        sent_after = sent_before + len(jobs)
        subject = f"Job Radar: {len(jobs)} new — {sent_after}/{daily_limit} today"
        html = _build_html(jobs, sent_before=sent_before, daily_limit=daily_limit)

        for attempt in range(3):
            try:
                resend.Emails.send({
                    "from": self.sender,
                    "to": [self.recipient],
                    "subject": subject,
                    "html": html,
                })
                logger.info("Email sent: %d jobs to %s", len(jobs), self.recipient)
                return True
            except Exception as e:
                if attempt < 2:
                    wait = 5 * (2 ** attempt)
                    logger.warning("Email send failed (attempt %d/3): %s — retrying in %ds", attempt + 1, e, wait)
                    time.sleep(wait)
                else:
                    logger.error("Email send failed after 3 attempts: %s", e)
        return False
