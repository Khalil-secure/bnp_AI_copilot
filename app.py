"""Render entry point — re-exports the FastAPI app."""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from testing_copilot.backend.agent import app  # noqa: F401
