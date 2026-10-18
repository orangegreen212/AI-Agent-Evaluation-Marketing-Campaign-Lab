"""Vercel serverless entry point: serves the FastAPI app under /v1/* (see vercel.json rewrites).

The lab package lives in ../src (not installed as a package on Vercel), so it is added to sys.path here.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from lab.api.app import create_app  # noqa: E402

app = create_app()
