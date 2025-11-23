"""FastAPI entry point for ConstructionBot."""

from __future__ import annotations

import os
import uuid
import logging
import asyncio
from pathlib import Path
from typing import List, Optional, Dict, Dict
from datetime import datetime
from contextlib import asynccontextmanager

from fastapi import FastAPI, File, HTTPException, UploadFile, Body, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel
from dotenv import load_dotenv

from .agent import agent_orchestrator
from .ingestion import ingest_payload, ingest_files, get_uploaded_files, delete_file
from .notifications_db import (
    create_smtp_config, update_smtp_config, list_smtp_configs, delete_smtp_config, get_smtp_config,
    create_recipient, update_recipient, list_recipients, delete_recipient, get_recipient,
    create_schedule, update_schedule, list_schedules, delete_schedule, get_schedule,
    get_notification_history,
    # Payment functions
    create_payment, update_payment, get_payment, list_payments, delete_payment,
    get_payments_due_soon, get_overdue_payments
)
from .notifications_service import notification_service
from .generate_mock_data import populate_mock_data
from .auth import (
    create_user, authenticate_user, create_access_token, get_current_user,
    UserCreate, UserLogin, init_auth_db
)

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

# Background task for checking and sending due notifications
# NOTE: Disabled for multi-user support - users should manually trigger notifications
# or we can implement per-user background tasks later
async def check_notifications_periodically():
    """Background task that checks for due notifications every hour."""
    # TODO: Implement per-user notification checking or disable background task
    # For now, users can manually trigger notifications via the API endpoint
    logger.info("⚠️  Background notification checking is disabled for multi-user support")
    logger.info("   Users can manually trigger notifications via /api/notifications/check-and-send")
    while True:
        try:
            await asyncio.sleep(3600)  # Wait 1 hour
            # Background task disabled - users must manually trigger notifications
            pass
        except Exception as e:
            logger.error(f"❌ Error in notification check task: {e}")
            import traceback
            logger.error(traceback.format_exc())


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifespan context manager for startup and shutdown."""
    # Startup: Initialize auth database
    logger.info("🔐 Initializing authentication database...")
    init_auth_db()
    logger.info("✅ Authentication database initialized")
    
    # Startup: Start background task
    logger.info("🚀 Starting notification scheduler background task...")
    task = asyncio.create_task(check_notifications_periodically())
    logger.info("✅ Notification scheduler started (checks every hour)")
    
    yield
    
    # Shutdown: Cancel background task
    logger.info("🛑 Shutting down notification scheduler...")
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass
    logger.info("✅ Notification scheduler stopped")


app = FastAPI(title="ConstructionBot API", version="1.0.0", lifespan=lifespan)

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


# Notification Pydantic models
class SMTPConfigCreate(BaseModel):
    name: str
    host: str
    port: int
    username: str
    password: str
    use_tls: bool = True
    from_email: str
    from_name: Optional[str] = None


class RecipientCreate(BaseModel):
    name: str
    email: str
    type: str  # vendor, worker, client
    phone: Optional[str] = None
    company: Optional[str] = None
    address: Optional[str] = None
    notes: Optional[str] = None
    smtp_config_id: Optional[int] = None


class ScheduleCreate(BaseModel):
    name: str
    recipient_id: int
    notification_type: str  # payment_reminder, payment_request, custom
    interval_days: int = 7
    enabled: bool = True
    trigger_condition: Optional[str] = None
    email_template: Optional[str] = None
    payment_link: Optional[str] = None


class NotificationSendRequest(BaseModel):
    schedule_id: Optional[int] = None
    recipient_id: Optional[int] = None
    notification_type: str
    context: Optional[Dict] = None
    template: Optional[str] = None
    payment_link: Optional[str] = None


# Notification Pydantic models
class SMTPConfigCreate(BaseModel):
    name: str
    host: str
    port: int
    username: str
    password: str
    use_tls: bool = True
    from_email: str
    from_name: Optional[str] = None


class RecipientCreate(BaseModel):
    name: str
    email: str
    type: str  # vendor, worker, client
    phone: Optional[str] = None
    company: Optional[str] = None
    address: Optional[str] = None
    notes: Optional[str] = None
    smtp_config_id: Optional[int] = None


class ScheduleCreate(BaseModel):
    name: str
    recipient_id: int
    notification_type: str  # payment_reminder, payment_request, custom
    interval_days: int = 7
    enabled: bool = True
    trigger_condition: Optional[str] = None
    email_template: Optional[str] = None
    payment_link: Optional[str] = None


class NotificationSendRequest(BaseModel):
    schedule_id: Optional[int] = None
    recipient_id: Optional[int] = None
    notification_type: str
    context: Optional[Dict] = None
    template: Optional[str] = None
    payment_link: Optional[str] = None


@app.get("/")
async def root():
    """Serve the frontend index.html file."""
    index_path = frontend_path / "index.html"
    return FileResponse(str(index_path))


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


# ==================== AUTHENTICATION ENDPOINTS ====================

@app.post("/api/auth/register")
async def register(user_data: UserCreate) -> dict:
    """Register a new user."""
    try:
        user = create_user(user_data.email, user_data.password, user_data.name)
        # JWT 'sub' claim must be a string
        user_id = str(user["id"])
        access_token = create_access_token(data={"sub": user_id})
        return {
            "success": True,
            "user": user,
            "access_token": access_token,
            "token_type": "bearer"
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/api/auth/login")
async def login(credentials: UserLogin) -> dict:
    """Login and get access token."""
    user = authenticate_user(credentials.email, credentials.password)
    if not user:
        raise HTTPException(
            status_code=401,
            detail="Incorrect email or password"
        )
    # JWT 'sub' claim must be a string
    user_id = str(user["id"])
    access_token = create_access_token(data={"sub": user_id})
    return {
        "success": True,
        "user": user,
        "access_token": access_token,
        "token_type": "bearer"
    }


@app.get("/api/auth/me")
async def get_current_user_info(current_user: dict = Depends(get_current_user)) -> dict:
    """Get current user information."""
    return {"user": current_user}


@app.post("/upload")
async def upload_files_legacy(
    pdfs: Optional[List[UploadFile]] = File(default=None),
    materials: Optional[List[UploadFile]] = File(default=None),
    workforce: Optional[List[UploadFile]] = File(default=None),
    current_user: dict = Depends(get_current_user)
) -> dict:
    """Legacy upload endpoint for backward compatibility."""
    pdfs = pdfs or []
    materials = materials or []
    workforce = workforce or []
    if not any([pdfs, materials, workforce]):
        raise HTTPException(status_code=400, detail="Provide at least one file to ingest.")

    ingestion_report = await ingest_payload(pdfs, materials, workforce, user_id=current_user["id"])
    return {"message": "Ingestion complete", **ingestion_report}


@app.post("/api/upload")
async def upload_files_generic(
    files: List[UploadFile] = File(...),
    current_user: dict = Depends(get_current_user)
) -> dict:
    """Generic file upload endpoint supporting all file types (PDF, DOCX, PPTX, CSV, Excel, images, etc.)."""
    if not files:
        raise HTTPException(status_code=400, detail="Provide at least one file to upload.")
    
    ingestion_report = await ingest_files(files, user_id=current_user["id"])
    return {"message": "Files uploaded and processed successfully", **ingestion_report}


@app.get("/api/files")
async def list_files(current_user: dict = Depends(get_current_user)) -> dict:
    """Get list of all uploaded files with metadata."""
    files = get_uploaded_files(user_id=current_user["id"])
    return {"files": files, "count": len(files)}


@app.delete("/api/files/{file_id:path}")
async def remove_file(file_id: str, current_user: dict = Depends(get_current_user)) -> dict:
    """Delete an uploaded file by ID."""
    success = delete_file(file_id, user_id=current_user["id"])
    if not success:
        raise HTTPException(status_code=404, detail="File not found.")
    return {"message": "File deleted successfully", "file_id": file_id}


@app.post("/chat")
async def chat(request: ChatRequest, current_user: dict = Depends(get_current_user)) -> dict:
    session_id = request.session_id or str(uuid.uuid4())
    logger.info(f"📨 Received chat request - User: {current_user['id']}, Session: {session_id}, Message length: {len(request.message)}")
    start_time = datetime.now()
    
    try:
        # Create user-specific agent orchestrator
        from .agent import get_agent_orchestrator
        user_agent = get_agent_orchestrator(current_user["id"])
        response = user_agent.run(request.message, session_id=session_id, user_id=current_user["id"])
        elapsed = (datetime.now() - start_time).total_seconds()
        logger.info(f"✅ Chat request completed in {elapsed:.2f}s - Session: {session_id}")
        return {"response": response, "session_id": session_id}
    except Exception as e:
        elapsed = (datetime.now() - start_time).total_seconds()
        logger.error(f"❌ Chat request failed after {elapsed:.2f}s - Session: {session_id}, Error: {str(e)}")
        raise


# ==================== NOTIFICATION API ENDPOINTS ====================

# SMTP Configuration endpoints
@app.post("/api/notifications/smtp")
async def create_smtp_config_endpoint(config: SMTPConfigCreate, current_user: dict = Depends(get_current_user)) -> dict:
    """Create a new SMTP configuration."""
    try:
        config_id = create_smtp_config(config.dict(), user_id=current_user["id"])
        return {"success": True, "id": config_id, "message": "SMTP configuration created"}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.get("/api/notifications/smtp")
async def list_smtp_configs_endpoint(current_user: dict = Depends(get_current_user)) -> dict:
    """List all SMTP configurations."""
    configs = list_smtp_configs(user_id=current_user["id"])
    return {"configs": configs, "count": len(configs)}


@app.get("/api/notifications/smtp/{config_id}")
async def get_smtp_config_endpoint(config_id: int, current_user: dict = Depends(get_current_user)) -> dict:
    """Get a specific SMTP configuration."""
    config = get_smtp_config(config_id=config_id, user_id=current_user["id"])
    if not config:
        raise HTTPException(status_code=404, detail="SMTP configuration not found")
    # Don't return password
    config.pop('password', None)
    return {"config": config}


@app.put("/api/notifications/smtp/{config_id}")
async def update_smtp_config_endpoint(config_id: int, config: SMTPConfigCreate, current_user: dict = Depends(get_current_user)) -> dict:
    """Update an SMTP configuration."""
    success = update_smtp_config(config_id, config.dict(), user_id=current_user["id"])
    if not success:
        raise HTTPException(status_code=404, detail="SMTP configuration not found")
    return {"success": True, "message": "SMTP configuration updated"}


@app.delete("/api/notifications/smtp/{config_id}")
async def delete_smtp_config_endpoint(config_id: int, current_user: dict = Depends(get_current_user)) -> dict:
    """Delete an SMTP configuration."""
    success = delete_smtp_config(config_id, user_id=current_user["id"])
    if not success:
        raise HTTPException(status_code=404, detail="SMTP configuration not found")
    return {"success": True, "message": "SMTP configuration deleted"}


# Recipient endpoints
@app.post("/api/notifications/recipients")
async def create_recipient_endpoint(recipient: RecipientCreate, current_user: dict = Depends(get_current_user)) -> dict:
    """Create a new recipient."""
    try:
        recipient_id = create_recipient(recipient.dict(), user_id=current_user["id"])
        return {"success": True, "id": recipient_id, "message": "Recipient created"}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.get("/api/notifications/recipients")
async def list_recipients_endpoint(type: Optional[str] = None, current_user: dict = Depends(get_current_user)) -> dict:
    """List all recipients."""
    recipients = list_recipients(user_id=current_user["id"], recipient_type=type)
    return {"recipients": recipients, "count": len(recipients)}


@app.get("/api/notifications/recipients/{recipient_id}")
async def get_recipient_endpoint(recipient_id: int, current_user: dict = Depends(get_current_user)) -> dict:
    """Get a specific recipient."""
    recipient = get_recipient(recipient_id, user_id=current_user["id"])
    if not recipient:
        raise HTTPException(status_code=404, detail="Recipient not found")
    return {"recipient": recipient}


@app.put("/api/notifications/recipients/{recipient_id}")
async def update_recipient_endpoint(recipient_id: int, recipient: RecipientCreate, current_user: dict = Depends(get_current_user)) -> dict:
    """Update a recipient."""
    success = update_recipient(recipient_id, recipient.dict(), user_id=current_user["id"])
    if not success:
        raise HTTPException(status_code=404, detail="Recipient not found")
    return {"success": True, "message": "Recipient updated"}


@app.delete("/api/notifications/recipients/{recipient_id}")
async def delete_recipient_endpoint(recipient_id: int, current_user: dict = Depends(get_current_user)) -> dict:
    """Delete a recipient."""
    success = delete_recipient(recipient_id, user_id=current_user["id"])
    if not success:
        raise HTTPException(status_code=404, detail="Recipient not found")
    return {"success": True, "message": "Recipient deleted"}


# Schedule endpoints
@app.post("/api/notifications/schedules")
async def create_schedule_endpoint(schedule: ScheduleCreate, current_user: dict = Depends(get_current_user)) -> dict:
    """Create a new notification schedule."""
    try:
        schedule_id = create_schedule(schedule.dict(), user_id=current_user["id"])
        return {"success": True, "id": schedule_id, "message": "Schedule created"}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.get("/api/notifications/schedules")
async def list_schedules_endpoint(enabled_only: bool = False, current_user: dict = Depends(get_current_user)) -> dict:
    """List all notification schedules."""
    schedules = list_schedules(user_id=current_user["id"], enabled_only=enabled_only)
    return {"schedules": schedules, "count": len(schedules)}


@app.get("/api/notifications/schedules/{schedule_id}")
async def get_schedule_endpoint(schedule_id: int, current_user: dict = Depends(get_current_user)) -> dict:
    """Get a specific schedule."""
    schedule = get_schedule(schedule_id, user_id=current_user["id"])
    if not schedule:
        raise HTTPException(status_code=404, detail="Schedule not found")
    return {"schedule": schedule}


@app.put("/api/notifications/schedules/{schedule_id}")
async def update_schedule_endpoint(schedule_id: int, schedule: ScheduleCreate, current_user: dict = Depends(get_current_user)) -> dict:
    """Update a schedule."""
    success = update_schedule(schedule_id, schedule.dict(), user_id=current_user["id"])
    if not success:
        raise HTTPException(status_code=404, detail="Schedule not found")
    return {"success": True, "message": "Schedule updated"}


@app.delete("/api/notifications/schedules/{schedule_id}")
async def delete_schedule_endpoint(schedule_id: int, current_user: dict = Depends(get_current_user)) -> dict:
    """Delete a schedule."""
    success = delete_schedule(schedule_id, user_id=current_user["id"])
    if not success:
        raise HTTPException(status_code=404, detail="Schedule not found")
    return {"success": True, "message": "Schedule deleted"}


# Notification sending endpoints
@app.post("/api/notifications/send")
async def send_notification_endpoint(request: NotificationSendRequest, current_user: dict = Depends(get_current_user)) -> dict:
    """Send a notification."""
    try:
        if request.schedule_id:
            result = notification_service.send_notification(
                schedule_id=request.schedule_id,
                user_id=current_user["id"],
                context=request.context,
                force=True
            )
        elif request.recipient_id:
            result = notification_service.send_direct_notification(
                recipient_id=request.recipient_id,
                user_id=current_user["id"],
                notification_type=request.notification_type,
                context=request.context,
                template=request.template,
                payment_link=request.payment_link
            )
        else:
            raise HTTPException(status_code=400, detail="Either schedule_id or recipient_id must be provided")
        
        if not result.get('success'):
            raise HTTPException(status_code=400, detail=result.get('error', 'Failed to send notification'))
        
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/notifications/check-and-send")
async def check_and_send_notifications_endpoint() -> dict:
    """Check and send due notifications. Can be called manually or runs automatically every hour."""
    logger.info("🔔 Manual notification check triggered")
    results = notification_service.check_and_send_due_notifications()
    logger.info(f"📊 Check complete: {len(results)} notification(s) processed")
    return {"results": results, "count": len(results), "message": f"Processed {len(results)} notification(s)"}


@app.get("/api/notifications/history")
async def get_notification_history_endpoint(limit: int = 100, recipient_id: Optional[int] = None, current_user: dict = Depends(get_current_user)) -> dict:
    """Get notification history."""
    history = get_notification_history(user_id=current_user["id"], limit=limit, recipient_id=recipient_id)
    return {"history": history, "count": len(history)}


# ==================== PAYMENTS API ENDPOINTS ====================
@app.post("/api/erp/payments")
async def create_payment_endpoint(payment: dict, current_user: dict = Depends(get_current_user)) -> dict:
    """Create a new payment record."""
    try:
        payment_id = create_payment(payment, user_id=current_user["id"])
        return {"success": True, "id": payment_id, "message": "Payment created"}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.get("/api/erp/payments")
async def list_payments_endpoint(
    payment_type: Optional[str] = None,
    entity_type: Optional[str] = None,
    status: Optional[str] = None,
    limit: Optional[int] = None,
    current_user: dict = Depends(get_current_user)
) -> dict:
    """List all payments."""
    payments = list_payments(
        user_id=current_user["id"],
        payment_type=payment_type,
        entity_type=entity_type,
        status=status,
        limit=limit
    )
    return {"payments": payments, "count": len(payments)}


@app.get("/api/erp/payments/due-soon")
async def get_payments_due_soon_endpoint(days: int = 7, current_user: dict = Depends(get_current_user)) -> dict:
    """Get payments due soon."""
    payments = get_payments_due_soon(user_id=current_user["id"], days=days)
    return {"payments": payments, "count": len(payments)}


@app.get("/api/erp/payments/overdue")
async def get_overdue_payments_endpoint(current_user: dict = Depends(get_current_user)) -> dict:
    """Get overdue payments."""
    payments = get_overdue_payments(user_id=current_user["id"])
    return {"payments": payments, "count": len(payments)}


@app.get("/api/erp/payments/{payment_id}")
async def get_payment_endpoint(payment_id: int, current_user: dict = Depends(get_current_user)) -> dict:
    """Get a specific payment."""
    payment = get_payment(payment_id, user_id=current_user["id"])
    if not payment:
        raise HTTPException(status_code=404, detail="Payment not found")
    return {"payment": payment}


@app.put("/api/erp/payments/{payment_id}")
async def update_payment_endpoint(payment_id: int, payment: dict, current_user: dict = Depends(get_current_user)) -> dict:
    """Update a payment record."""
    success = update_payment(payment_id, payment, user_id=current_user["id"])
    if not success:
        raise HTTPException(status_code=404, detail="Payment not found")
    return {"success": True, "message": "Payment updated"}


@app.delete("/api/erp/payments/{payment_id}")
async def delete_payment_endpoint(payment_id: int, current_user: dict = Depends(get_current_user)) -> dict:
    """Delete a payment record."""
    success = delete_payment(payment_id, user_id=current_user["id"])
    if not success:
        raise HTTPException(status_code=404, detail="Payment not found")
    return {"success": True, "message": "Payment deleted"}


# Mock data endpoint
@app.post("/api/erp/generate-mock-data")
async def generate_mock_data_endpoint() -> dict:
    """Generate mock ERP data."""
    try:
        populate_mock_data()
        return {"success": True, "message": "Mock data generated successfully"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/erp/payments/{payment_id}/reminders")
async def get_payment_reminders_endpoint(payment_id: int) -> dict:
    """Get existing reminder schedules for a payment."""
    from .notifications_db import list_schedules
    schedules = list_schedules(enabled_only=False)
    payment_schedules = [s for s in schedules if s.get('payment_id') == payment_id and s.get('schedule_type') == 'before_due']
    return {"schedules": payment_schedules, "count": len(payment_schedules), "exists": len(payment_schedules) > 0}


@app.post("/api/erp/payments/{payment_id}/create-reminders")
async def create_payment_reminders_endpoint(
    payment_id: int, 
    request: Dict = Body(default={}),
    current_user: dict = Depends(get_current_user)
) -> dict:
    """Create or update automatic reminder schedules for a payment."""
    try:
        from .notifications_db import list_schedules, delete_schedule
        
        # Check if reminders already exist for this payment
        schedules = list_schedules(user_id=current_user["id"], enabled_only=False)
        existing_schedules = [s for s in schedules if s.get('payment_id') == payment_id and s.get('schedule_type') == 'before_due']
        
        # Delete existing reminders if updating (this ensures we update, not duplicate)
        deleted_count = 0
        if existing_schedules:
            for schedule in existing_schedules:
                delete_schedule(schedule['id'], user_id=current_user["id"])
                deleted_count += 1
            logger.info(f"Deleted {deleted_count} existing reminder schedule(s) for payment {payment_id}")
        
        days_before = request.get('days_before', [7, 3, 1])
        email_template = request.get('email_template')
        
        # Create new schedules (this replaces the old ones)
        schedule_ids = notification_service.create_payment_based_schedules(
            payment_id,
            user_id=current_user["id"],
            days_before=days_before,
            email_template=email_template
        )
        return {
            "success": True, 
            "schedule_ids": schedule_ids, 
            "count": len(schedule_ids), 
            "updated": deleted_count > 0,
            "deleted_count": deleted_count
        }
    except Exception as e:
        import traceback
        logger.error(f"Error creating payment reminders: {e}\n{traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=str(e))


