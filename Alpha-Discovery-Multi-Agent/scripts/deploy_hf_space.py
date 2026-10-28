"""Stage the backend and the data it needs, then upload it to a free Hugging Face Space.

    set HF_TOKEN=hf_xxx            (a token with write access, created at huggingface.co/settings/tokens)
    python scripts/deploy_hf_space.py --space YOUR_USERNAME/alpha-discovery-api [--dry-run]

Only the read-only dashboard data is uploaded (about 2.4 GB, mostly storage/quant.duckdb).
API keys are never uploaded; set them as Space secrets if you ever need them.
"""
import argparse, os, shutil, sys, tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ap = argparse.ArgumentParser()
ap.add_argument("--space", required=True)
ap.add_argument("--dry-run", action="store_true")
a = ap.parse_args()

stage = Path(tempfile.mkdtemp(prefix="hf_space_"))
shutil.copytree(ROOT / "app", stage / "app", ignore=shutil.ignore_patterns("__pycache__"))
for f in ("Dockerfile", "requirements-api.txt", "README.md"):
    shutil.copy(ROOT / "deploy" / "hf_space" / f, stage / f)
for rel in ("data/config", "data/alpha/results", "data/alpha/experiments", "data/alpha/llm", "data/processed/regime", "data/processed/sec", "data/manifests", "docs/paper"):
    src = ROOT / rel
    if src.exists():
        shutil.copytree(src, stage / rel)
db = ROOT / "storage" / "quant.duckdb"
if db.exists():
    (stage / "storage").mkdir(exist_ok=True)
    shutil.copy(db, stage / "storage" / "quant.duckdb")
else:
    print("WARNING: storage/quant.duckdb not found next to the code; the dashboard data pages will be empty.")
size = sum(p.stat().st_size for p in stage.rglob("*") if p.is_file()) / 1e9
print(f"staged {size:.2f} GB in {stage}")
if a.dry_run:
    sys.exit(0)
from huggingface_hub import HfApi
api = HfApi(token=os.environ["HF_TOKEN"])
api.create_repo(a.space, repo_type="space", space_sdk="docker", exist_ok=True)
api.upload_folder(folder_path=str(stage), repo_id=a.space, repo_type="space")
print("uploaded. Your API will be at https://" + a.space.replace("/", "-").lower() + ".hf.space")
