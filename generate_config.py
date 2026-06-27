"""
Generates config.yaml from environment variables.
Used by entrypoint.sh when deploying to cloud (Railway, Fly.io, etc.)
where config.yaml cannot be volume-mounted.

Required env vars:
  GEMINI_API_KEY, EMAIL_SENDER, EMAIL_APP_PASSWORD, EMAIL_RECIPIENT

Optional env vars (have sensible defaults):
  GROQ_API_KEY, GITHUB_USERNAME, GITHUB_TOKEN,
  LLM_THRESHOLD, SEMANTIC_THRESHOLD, DAILY_JOB_LIMIT
"""
import os
import sys

required = ["GEMINI_API_KEY", "EMAIL_SENDER", "EMAIL_APP_PASSWORD", "EMAIL_RECIPIENT"]
missing = [v for v in required if not os.environ.get(v)]
if missing:
    print(f"[generate_config] ERROR: Missing required env vars: {', '.join(missing)}")
    sys.exit(1)

config = f"""schedule:
  remote_minutes: 30
  jobspy_hours: 3

filters:
  keywords:
    # Core AI/ML titles
    - AI engineer
    - ML engineer
    - machine learning engineer
    - machine learning
    - deep learning
    - MLOps
    - data scientist
    - data engineer
    - data science
    - LLM
    - large language model
    - generative AI
    - NLP
    - natural language processing
    - computer vision
    - PyTorch
    - TensorFlow
    - model serving
    - vector database
    - AI researcher
    - applied scientist
    - AI scientist
    # AI/ML techniques
    - RAG
    - fine-tuning
    - fine tuning
    - Hugging Face
    - transformer
    - reinforcement learning
    - recommendation system
    - recommender
    - diffusion model
    - multimodal
    - foundation model
    - inference engineer
    - embedding
    # Data engineering
    - analytics engineer
    - data pipeline
    - ETL
    - Spark
    - dbt
    - Kafka
    # Software roles in AI companies
    - Python engineer
    - Python developer
    - research engineer
    - backend engineer
    - software engineer
  exclude_keywords:
    - 10+ years
    - 7+ years
    - 5+ years
    - principal engineer
    - "VP of"
    - staff engineer
    - director
    - senior engineer
    - lead engineer
    - "senior data"
    - "senior ML"
    - "senior machine"
    - "senior Python"
    - "senior backend"
    - "senior software"
    - "senior research"
    - "senior analytics"
    - "lead Python"
    - "lead backend"
    - "lead software"
  locations:
    - Lahore
    - Islamabad
  salary:
    min_pkr: 75000
    min_usd: 600
  seniority_allowed:
    - entry
    - associate
    - intern

github:
  username: "{os.environ.get('GITHUB_USERNAME', '')}"
  token: "{os.environ.get('GITHUB_TOKEN', '')}"
  max_repos: 20
  include_readme: true

scoring:
  semantic_threshold: {os.environ.get('SEMANTIC_THRESHOLD', '0.60')}
  llm_threshold: {os.environ.get('LLM_THRESHOLD', '80')}
  daily_job_limit: {os.environ.get('DAILY_JOB_LIMIT', '20')}
  gemini_api_key: "{os.environ.get('GEMINI_API_KEY')}"
  groq_api_key: "{os.environ.get('GROQ_API_KEY', '')}"

email:
  sender: "{os.environ.get('EMAIL_SENDER')}"
  app_password: "{os.environ.get('EMAIL_APP_PASSWORD')}"
  recipient: "{os.environ.get('EMAIL_RECIPIENT')}"

sources:
  jobspy:
    enabled: true
    sites:
      - indeed
    results_per_site: 30
    locations:
      - "Lahore, Pakistan"
      - "Islamabad, Pakistan"
      - "Remote"
  weworkremotely:
    enabled: true
  remoteok:
    enabled: true
  remoteco:
    enabled: true
  remotive:
    enabled: true
    categories:
      - software-dev
      - data
    limit_per_category: 50
  workatastartup:
    enabled: true
"""

with open("/app/config.yaml", "w", encoding="utf-8") as f:
    f.write(config)

print("[generate_config] config.yaml written successfully.")
