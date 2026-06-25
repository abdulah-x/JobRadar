import logging
import time
from typing import Optional

from .resume_processor import ResumeProcessor

logger = logging.getLogger(__name__)


class SemanticFilter:
    def __init__(self, resume_processor: ResumeProcessor, threshold: float = 0.45):
        self.processor = resume_processor
        self.threshold = threshold

    def score(self, job_description: str) -> Optional[float]:
        """Returns cosine similarity (0–1) between job and resume, or None on error."""
        try:
            client = self.processor.get_genai_client()
            result = client.models.embed_content(
                model="gemini-embedding-001",
                contents=job_description[:2000],
            )
            job_embedding = result.embeddings[0].values

            collection = self.processor.get_collection()
            results = collection.query(
                query_embeddings=[job_embedding],
                n_results=min(3, collection.count()),
                include=["distances"],
            )
            if not results["distances"] or not results["distances"][0]:
                return None

            # ChromaDB returns L2 distances; convert to cosine-like similarity
            distances = results["distances"][0]
            avg_distance = sum(distances) / len(distances)
            similarity = max(0.0, 1.0 - avg_distance / 2.0)
            return round(similarity, 4)
        except Exception as e:
            logger.warning("Semantic filter error: %s", e)
            return None

    def passes(self, job_description: str) -> tuple[bool, float]:
        """Returns (passes_threshold, similarity_score)."""
        similarity = self.score(job_description)
        if similarity is None:
            return True, 0.0  # on error, let the job through to LLM scoring
        time.sleep(0.05)  # gentle rate limiting
        return similarity >= self.threshold, similarity
