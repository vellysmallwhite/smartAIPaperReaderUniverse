from fastapi import FastAPI
from server.main import app as fastapi_app

# Expose FastAPI app for Uvicorn when running `python -m uvicorn server.main:app` (Dockerfile CMD)
app = fastapi_app

