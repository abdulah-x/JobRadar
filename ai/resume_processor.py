import hashlib
import json
import logging
import re
import time
from pathlib import Path

import chromadb
from google import genai

from .models import ProfileSummary

logger = logging.getLogger(__name__)

COLLECTION_NAME = "resume_chunks"
HASH_FILE = "resume_hash.txt"


_DEFAULT_GEMINI_MODEL = "gemini-2.5-flash"


class ResumeProcessor:
    def __init__(self, resume_path: str, data_dir: str, gemini_api_key: str, gemini_model: str = _DEFAULT_GEMINI_MODEL):
        self.resume_path = Path(resume_path)
        self.data_dir = Path(data_dir)
        self.profile_path = self.data_dir / "profile.json"
        self.hash_path = self.data_dir / HASH_FILE
        self._gemini_model = gemini_model

        self._genai = genai.Client(api_key=gemini_api_key)
        self._client = chromadb.PersistentClient(path=str(self.data_dir / "chroma"))
        self._collection = None

    def get_genai_client(self) -> genai.Client:
        return self._genai

    def get_collection(self) -> chromadb.Collection:
        if self._collection is None:
            self._collection = self._client.get_or_create_collection(COLLECTION_NAME)
        return self._collection

    def _resume_hash(self) -> str:
        return hashlib.md5(self.resume_path.read_bytes()).hexdigest()

    def _stored_hash(self) -> str:
        if self.hash_path.exists():
            return self.hash_path.read_text().strip()
        return ""

    def needs_rebuild(self) -> bool:
        return self._resume_hash() != self._stored_hash()

    def build(self) -> ProfileSummary:
        if not self.resume_path.exists():
            raise FileNotFoundError(
                f"resume.txt not found at {self.resume_path}. "
                "Place your resume as plain text in that file before starting."
            )

        try:
            resume_text = self.resume_path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            resume_text = self.resume_path.read_text(encoding="latin-1")
        logger.info("Building resume index from %s", self.resume_path)

        chunks = self._chunk_resume(resume_text)
        self._embed_chunks(chunks)

        profile = self._extract_profile(resume_text)
        self.profile_path.write_text(profile.model_dump_json(indent=2), encoding="utf-8")
        self.hash_path.write_text(self._resume_hash(), encoding="utf-8")

        logger.info("Resume indexed: %d chunks, profile saved", len(chunks))
        return profile

    def load_profile(self) -> ProfileSummary:
        if self.profile_path.exists():
            return ProfileSummary.model_validate_json(self.profile_path.read_text(encoding="utf-8"))
        return ProfileSummary()

    def _chunk_resume(self, text: str) -> list[str]:
        section_headers = re.compile(
            r"^(SKILLS?|EXPERIENCE|EDUCATION|PROJECTS?|CERTIFICATIONS?|SUMMARY|OBJECTIVE|ABOUT)",
            re.IGNORECASE | re.MULTILINE,
        )
        positions = [m.start() for m in section_headers.finditer(text)]
        if not positions:
            # fallback: split into 500-char overlapping windows
            return [text[i:i+500] for i in range(0, len(text), 400)]

        chunks = []
        for i, pos in enumerate(positions):
            end = positions[i + 1] if i + 1 < len(positions) else len(text)
            chunk = text[pos:end].strip()
            if chunk:
                chunks.append(chunk)
        return chunks

    def _embed_chunks(self, chunks: list[str]) -> None:
        collection = self.get_collection()
        collection.delete(where={"source": "resume"})

        for i, chunk in enumerate(chunks):
            try:
                result = self._genai.models.embed_content(
                    model="gemini-embedding-001",
                    contents=chunk,
                )
                collection.add(
                    ids=[f"chunk_{i}"],
                    embeddings=[result.embeddings[0].values],
                    documents=[chunk],
                    metadatas=[{"source": "resume", "index": i}],
                )
                time.sleep(0.1)  # stay well within free-tier rate limit
            except Exception as e:
                logger.warning("Failed to embed chunk %d: %s", i, e)

    def _extract_profile(self, resume_text: str) -> ProfileSummary:
        prompt = f"""Extract a structured profile from the resume below.
Return ONLY valid JSON matching this schema:
{{
  "name": string,
  "skills": [string],
  "experience_years": integer,
  "domains": [string],
  "seniority": "junior" | "mid" | "senior",
  "preferred_roles": [string]
}}

Rules:
- experience_years: count only paid professional work (internships count as 0.5 each). Round to nearest integer, minimum 0.
- seniority: "junior" if experience_years < 2, "mid" if 2-5, "senior" if 5+. Students still in university are always "junior".
- skills: include ALL technical skills mentioned, no limit.

RESUME:
{resume_text[:3000]}"""
        for attempt in range(3):
            try:
                response = self._genai.models.generate_content(
                    model=self._gemini_model,
                    contents=prompt,
                )
                raw = response.text.strip()
                raw = re.sub(r"^```json\s*", "", raw)
                raw = re.sub(r"\s*```$", "", raw)
                data = json.loads(raw)
                return ProfileSummary(**data)
            except Exception as e:
                if attempt < 2:
                    wait = 5 * (2 ** attempt)  # 5s, 10s
                    logger.warning("Profile extraction attempt %d/3 failed: %s — retrying in %ds", attempt + 1, e, wait)
                    time.sleep(wait)
                else:
                    logger.error("Profile extraction failed after 3 attempts: %s — using empty profile", e)
        return ProfileSummary()
