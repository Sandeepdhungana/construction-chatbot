"""FastAPI entry point for ConstructionBot."""

from __future__ import annotations

import os
import uuid
import logging
from pathlib import Path
from typing import List, Optional
from datetime import datetime

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel
from dotenv import load_dotenv

from .agent import agent_orchestrator
from .ingestion import ingest_payload, ingest_files, get_uploaded_files, delete_file

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)

# Load .env file from project root (parent of backend directory)
env_path = Path(__file__).parent.parent / ".env"
load_dotenv(dotenv_path=env_path)

if not os.getenv("OPENAI_API_KEY"):
    raise RuntimeError(
        f"OPENAI_API_KEY must be set in the environment. "
        f"Checked .env file at: {env_path.absolute()}"
    )

app = FastAPI(title="ConstructionBot API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount static files directory
frontend_path = Path(__file__).parent.parent / "frontend"
app.mount("/static", StaticFiles(directory=str(frontend_path)), name="static")


class ChatRequest(BaseModel):
    message: str
    session_id: Optional[str] = None


@app.get("/")
async def root():
    """Serve the frontend index.html file."""
    index_path = frontend_path / "index.html"
    return FileResponse(str(index_path))


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


@app.post("/upload")
async def upload_files_legacy(
    pdfs: Optional[List[UploadFile]] = File(default=None),
    materials: Optional[List[UploadFile]] = File(default=None),
    workforce: Optional[List[UploadFile]] = File(default=None),
) -> dict:
    """Legacy upload endpoint for backward compatibility."""
    pdfs = pdfs or []
    materials = materials or []
    workforce = workforce or []
    if not any([pdfs, materials, workforce]):
        raise HTTPException(status_code=400, detail="Provide at least one file to ingest.")

    ingestion_report = await ingest_payload(pdfs, materials, workforce)
    return {"message": "Ingestion complete", **ingestion_report}


@app.post("/api/upload")
async def upload_files_generic(
    files: List[UploadFile] = File(...),
) -> dict:
    """Generic file upload endpoint supporting all file types (PDF, DOCX, PPTX, CSV, Excel, images, etc.)."""
    if not files:
        raise HTTPException(status_code=400, detail="Provide at least one file to upload.")
    
    ingestion_report = await ingest_files(files)
    return {"message": "Files uploaded and processed successfully", **ingestion_report}


@app.get("/api/files")
async def list_files() -> dict:
    """Get list of all uploaded files with metadata."""
    files = get_uploaded_files()
    return {"files": files, "count": len(files)}


@app.delete("/api/files/{file_id:path}")
async def remove_file(file_id: str) -> dict:
    """Delete an uploaded file by ID."""
    success = delete_file(file_id)
    if not success:
        raise HTTPException(status_code=404, detail="File not found.")
    return {"message": "File deleted successfully", "file_id": file_id}


@app.post("/chat")
async def chat(request: ChatRequest) -> dict:
    session_id = request.session_id or str(uuid.uuid4())
    logger.info(f"📨 Received chat request - Session: {session_id}, Message length: {len(request.message)}")
    start_time = datetime.now()
    
    try:
        response = agent_orchestrator.run(request.message, session_id=session_id)
        elapsed = (datetime.now() - start_time).total_seconds()
        logger.info(f"✅ Chat request completed in {elapsed:.2f}s - Session: {session_id}")
        return {"response": response, "session_id": session_id}
    except Exception as e:
        elapsed = (datetime.now() - start_time).total_seconds()
        logger.error(f"❌ Chat request failed after {elapsed:.2f}s - Session: {session_id}, Error: {str(e)}")
        raise


