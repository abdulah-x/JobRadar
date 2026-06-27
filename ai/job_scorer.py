import logging
import re
import threading
import time

from google.genai import types

from .models import ProfileSummary, ScoringResult
from .resume_processor import ResumeProcessor

logger = logging.getLogger(__name__)

# Global lock — ensures only one Gemini Flash call runs at a time across all pipeline threads
_gemini_lock = threading.Lock()

SCORE_PROMPT = """You are a job-resume matching assistant evaluating roles for a candidate based in Pakistan (Lahore or Islamabad).

Candidate profile:
- Seniority: {seniority}
- Skills: {skills}
- Domains: {domains}
- Experience: {experience_years} years

Most relevant resume sections for this job:
{resume_chunks}

Job to evaluate:
Title: {title}
Company: {company}
Description:
{job_description}

Evaluate this job and return a JSON object with the following fields:

score (0-100): How well the candidate's skills match the job requirements. 100 = perfect match.

matching_skills: Skills from the candidate profile that match job requirements.

missing_skills: Skills the job requires that the candidate lacks.

reason: One sentence explaining the score.

seniority_match: True if the role level is compatible with the candidate's experience (entry/junior/associate/intern roles match a candidate with 0-2 years experience).

seniority_level: Classify the role as exactly one of: "entry", "associate", "intern", "mid", "senior", "unknown".
  - "entry": explicitly says entry-level, 0-1 year, fresh graduate, junior, trainee
  - "associate": associate engineer/scientist, 1-2 years
  - "intern": internship (paid or unpaid)
  - "mid": 2-5 years, mid-level
  - "senior": 5+ years, senior, lead, principal, staff
  - "unknown": seniority cannot be determined

location_ok: True if ANY of these apply:
  1. Job location is Lahore or Islamabad (Pakistan)
  2. Job is remote AND does NOT explicitly require work authorization, visa, or residency in a specific country
  False if: job is on-site in a city other than Lahore/Islamabad, OR remote but requires US/EU/specific country residency or work permit.

salary_ok: True unless the job explicitly states a salary that is below PKR 75,000/month OR below USD 600/month. If salary is not mentioned, return true.

requires_visa: True if the job says anything like "must be authorized to work in [country]", "visa sponsorship not provided", "EU work permit required", "must be US-based", etc. False otherwise."""


class JobScorer:
    def __init__(self, resume_processor: ResumeProcessor, profile: ProfileSummary, groq_api_key: str = ""):
        self.processor = resume_processor
        self.profile = profile
        self._client = resume_processor.get_genai_client()
        self._groq = None
        if groq_api_key and groq_api_key != "YOUR_GROQ_API_KEY":
            try:
                from groq import Groq
                self._groq = Groq(api_key=groq_api_key)
                logger.info("Groq fallback enabled (llama-3.3-70b-versatile)")
            except Exception as e:
                logger.warning("Groq init failed — fallback disabled: %s", e)

    def score(self, title: str, company: str, job_description: str) -> ScoringResult:
        resume_chunks = self._retrieve_chunks(job_description)
        prompt = SCORE_PROMPT.format(
            seniority=self.profile.seniority,
            skills=", ".join(self.profile.skills) if self.profile.skills else "Not specified",
            domains=", ".join(self.profile.domains) if self.profile.domains else "Not specified",
            experience_years=self.profile.experience_years,
            resume_chunks=resume_chunks,
            title=title,
            company=company,
            job_description=job_description[:2500],
        )

        for attempt in range(3):
            try:
                with _gemini_lock:
                    time.sleep(15)  # pace to 5 RPM; lock held across sleep + call so threads queue up
                    response = self._client.models.generate_content(
                        model="gemini-2.5-flash",
                        contents=prompt,
                        config=types.GenerateContentConfig(
                            response_mime_type="application/json",
                            response_schema={
                                "type": "object",
                                "properties": {
                                    "score": {"type": "integer"},
                                    "matching_skills": {"type": "array", "items": {"type": "string"}},
                                    "missing_skills": {"type": "array", "items": {"type": "string"}},
                                    "reason": {"type": "string"},
                                    "seniority_match": {"type": "boolean"},
                                    "seniority_level": {
                                        "type": "string",
                                        "enum": ["entry", "associate", "intern", "mid", "senior", "unknown"],
                                    },
                                    "location_ok": {"type": "boolean"},
                                    "salary_ok": {"type": "boolean"},
                                    "requires_visa": {"type": "boolean"},
                                },
                                "required": [
                                    "score", "matching_skills", "missing_skills", "reason",
                                    "seniority_match", "seniority_level", "location_ok",
                                    "salary_ok", "requires_visa",
                                ],
                            },
                        ),
                    )
                return ScoringResult.model_validate_json(response.text)
            except Exception as e:
                err_str = str(e)
                is_rate_limit = "429" in err_str or "RESOURCE_EXHAUSTED" in err_str
                if self._groq:
                    log_reason = "rate-limited" if is_rate_limit else f"error: {e}"
                    logger.warning("Gemini failed for '%s' (%s) — falling back to Groq", title, log_reason)
                    result = self._score_with_groq(prompt, title)
                    if result:
                        return result
                if attempt < 2:
                    if is_rate_limit:
                        match = re.search(r"retryDelay.*?(\d+)s", err_str)
                        wait = int(match.group(1)) + 5 if match else 30 * (2 ** attempt)
                        logger.warning("Gemini attempt %d rate-limited for '%s' — waiting %ds", attempt + 1, title, wait)
                        time.sleep(wait)
                    else:
                        wait = 3 * (2 ** attempt)  # 3s, 6s
                        logger.warning("Scoring attempt %d failed for '%s': %s — retrying in %ds", attempt + 1, title, e, wait)
                        time.sleep(wait)
                else:
                    logger.error("Scoring failed for '%s': %s — skipping", title, e)

        return ScoringResult(
            score=0,
            reason="Scoring failed",
            seniority_match=False,
            seniority_level="unknown",
            location_ok=True,
            salary_ok=True,
            requires_visa=False,
        )

    def _score_with_groq(self, prompt: str, title: str) -> ScoringResult | None:
        try:
            response = self._groq.chat.completions.create(
                model="llama-3.3-70b-versatile",
                messages=[
                    {"role": "system", "content": "You are a job-resume matching assistant. Respond with valid JSON only."},
                    {"role": "user", "content": prompt[:6000]},
                ],
                response_format={"type": "json_object"},
                temperature=0.1,
                max_tokens=800,
            )
            result = ScoringResult.model_validate_json(response.choices[0].message.content)
            logger.info("Groq fallback succeeded for '%s'", title)
            return result
        except Exception as e:
            logger.warning("Groq fallback failed for '%s': %s", title, e)
            return None

    def _retrieve_chunks(self, job_description: str) -> str:
        try:
            result = self._client.models.embed_content(
                model="gemini-embedding-001",
                contents=job_description[:2000],
            )
            collection = self.processor.get_collection()
            results = collection.query(
                query_embeddings=[result.embeddings[0].values],
                n_results=min(3, collection.count()),
                include=["documents"],
            )
            chunks = results.get("documents", [[]])[0]
            return "\n---\n".join(chunks) if chunks else "No resume chunks available."
        except Exception as e:
            logger.warning("Chunk retrieval failed: %s", e)
            return "Resume context unavailable."
