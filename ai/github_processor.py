import base64
import hashlib
import json
import logging
import time
from pathlib import Path

from google import genai
import requests

logger = logging.getLogger(__name__)

_GITHUB_API = "https://api.github.com"


class GitHubProcessor:
    def __init__(
        self,
        username: str,
        data_dir: str,
        gemini_api_key: str,
        token: str = None,
        max_repos: int = 20,
        include_readme: bool = True,
    ):
        self.username = username
        self.data_dir = Path(data_dir)
        self.gemini_api_key = gemini_api_key
        self.max_repos = max_repos
        self.include_readme = include_readme
        self.hash_path = self.data_dir / "github_hash.txt"

        self._session = requests.Session()
        self._session.headers.update({"Accept": "application/vnd.github+json"})
        if token:
            self._session.headers.update({"Authorization": f"Bearer {token}"})

        self._genai = genai.Client(api_key=gemini_api_key)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def needs_rebuild(self) -> bool:
        repos = self._fetch_repo_list()
        if not repos:
            return False
        current_hash = self._hash_repos(repos)
        if not self.hash_path.exists():
            return True
        return self.hash_path.read_text().strip() != current_hash

    def build(self, collection) -> int:
        """Fetch repos, embed as chunks, store in ChromaDB. Returns number of chunks stored."""
        repos = self._fetch_repo_list()
        if not repos:
            logger.warning("GitHub: no public repos found for user '%s'", self.username)
            return 0

        chunks, ids, metadatas = [], [], []
        for i, repo in enumerate(repos):
            text = self._repo_to_text(repo)
            chunks.append(text)
            ids.append(f"github_{i}")
            metadatas.append({"source": "github", "repo": repo["name"]})

        # wipe existing GitHub chunks before re-inserting
        try:
            collection.delete(where={"source": "github"})
        except Exception as e:
            logger.debug("GitHub chunk delete skipped (may be first run): %s", e)

        # embed and store
        embeddings = []
        for i, chunk in enumerate(chunks):
            try:
                result = self._genai.models.embed_content(
                    model="gemini-embedding-001",
                    contents=chunk,
                )
                embeddings.append(result.embeddings[0].values)
            except Exception as e:
                logger.warning("GitHub: embedding failed for repo '%s': %s", ids[i], e)
                embeddings.append(None)
            time.sleep(0.1)

        # filter out any that failed to embed
        valid = [
            (chunk, emb, id_, meta)
            for chunk, emb, id_, meta in zip(chunks, embeddings, ids, metadatas)
            if emb is not None
        ]

        if valid:
            collection.add(
                documents=[v[0] for v in valid],
                embeddings=[v[1] for v in valid],
                ids=[v[2] for v in valid],
                metadatas=[v[3] for v in valid],
            )

        # save hash
        current_hash = self._hash_repos(repos)
        self.hash_path.write_text(current_hash)

        logger.info("GitHub: indexed %d/%d repos into ChromaDB", len(valid), len(repos))
        return len(valid)

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _fetch_repo_list(self) -> list[dict]:
        url = f"{_GITHUB_API}/users/{self.username}/repos"
        params = {"sort": "updated", "per_page": self.max_repos, "type": "owner"}
        try:
            resp = self._session.get(url, params=params, timeout=15)
            resp.raise_for_status()
            repos = resp.json()
            # skip forks — only the user's own work
            return [r for r in repos if not r.get("fork", False)]
        except Exception as e:
            logger.warning("GitHub: failed to fetch repo list: %s", e)
            return []

    def _fetch_readme(self, repo_name: str) -> str:
        url = f"{_GITHUB_API}/repos/{self.username}/{repo_name}/readme"
        try:
            resp = self._session.get(url, timeout=10)
            if resp.status_code == 404:
                return ""
            resp.raise_for_status()
            data = resp.json()
            raw = base64.b64decode(data["content"]).decode("utf-8", errors="ignore")
            return raw[:1000]
        except Exception:
            return ""

    def _fetch_languages(self, repo_name: str) -> list[str]:
        url = f"{_GITHUB_API}/repos/{self.username}/{repo_name}/languages"
        try:
            resp = self._session.get(url, timeout=10)
            resp.raise_for_status()
            return list(resp.json().keys())
        except Exception:
            return []

    def _repo_to_text(self, repo: dict) -> str:
        name = repo.get("name", "")
        description = repo.get("description") or ""
        topics = ", ".join(repo.get("topics", []))
        languages = self._fetch_languages(name)
        lang_str = ", ".join(languages) if languages else "unknown"

        readme = ""
        if self.include_readme:
            time.sleep(0.3)  # gentle rate limiting between API calls
            readme = self._fetch_readme(name)

        parts = [
            f"Project: {name}",
            f"Description: {description}" if description else "",
            f"Languages: {lang_str}",
            f"Topics: {topics}" if topics else "",
        ]
        if readme.strip():
            parts.append(f"README:\n{readme.strip()}")

        return "\n".join(p for p in parts if p)

    def _hash_repos(self, repos: list[dict]) -> str:
        fingerprint = json.dumps(
            [
                {
                    "name": r.get("name"),
                    "pushed_at": r.get("pushed_at"),
                    "description": r.get("description"),
                    "topics": r.get("topics", []),
                }
                for r in repos
            ],
            sort_keys=True,
        )
        return hashlib.md5(fingerprint.encode()).hexdigest()
