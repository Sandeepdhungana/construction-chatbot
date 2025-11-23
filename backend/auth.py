"""Authentication and user management module."""

from __future__ import annotations

import os
from jose import jwt
from datetime import datetime, timedelta
from typing import Optional, Dict
from passlib.context import CryptContext
from fastapi import HTTPException, status, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel, EmailStr

from .notifications_db import get_db, init_db

# Password hashing
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# JWT settings
SECRET_KEY = os.getenv("JWT_SECRET_KEY", "your-secret-key-change-in-production")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 24 * 7  # 7 days

# HTTP Bearer token
# Set auto_error=False to handle errors ourselves
security = HTTPBearer(auto_error=False)


class UserCreate(BaseModel):
    """User registration model."""
    email: EmailStr
    password: str
    name: Optional[str] = None


class UserLogin(BaseModel):
    """User login model."""
    email: EmailStr
    password: str


class User(BaseModel):
    """User model."""
    id: int
    email: str
    name: Optional[str]
    created_at: str


def init_auth_db():
    """Initialize users table in database."""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                email TEXT NOT NULL UNIQUE,
                password_hash TEXT NOT NULL,
                name TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        # Create index on email for faster lookups
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_users_email ON users(email)
        """)


def hash_password(password: str) -> str:
    """Hash a password. Bcrypt has a 72-byte limit, so we truncate if necessary."""
    # Ensure password is a string
    if not isinstance(password, str):
        password = str(password)
    
    # Bcrypt has a 72-byte limit, so truncate if password is too long
    password_bytes = password.encode('utf-8')
    if len(password_bytes) > 72:
        # Truncate to 72 bytes
        password_bytes = password_bytes[:72]
        password = password_bytes.decode('utf-8', errors='ignore')
    
    try:
        return pwd_context.hash(password)
    except (ValueError, AttributeError) as e:
        # Handle bcrypt version compatibility issues
        error_msg = str(e)
        import logging
        logger = logging.getLogger(__name__)
        logger.error(f"Password hashing error: {e}")
        
        # Check if it's a bcrypt version issue
        if "__about__" in error_msg or "AttributeError" in str(type(e).__name__):
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Password hashing service error. Please ensure bcrypt>=4.0.0,<5.0.0 is installed."
            )
        
        # Check if it's a length issue
        if "72" in error_msg.lower() or "bytes" in error_msg.lower():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Password is too long. Maximum 72 characters allowed."
            )
        
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Error hashing password: {error_msg}"
        )
    except Exception as e:
        # Catch any other unexpected errors
        import logging
        logger = logging.getLogger(__name__)
        logger.error(f"Unexpected password hashing error: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Unexpected error processing password"
        )


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify a password against its hash."""
    return pwd_context.verify(plain_password, hashed_password)


def create_user(email: str, password: str, name: Optional[str] = None) -> Dict:
    """Create a new user."""
    import logging
    logger = logging.getLogger(__name__)
    
    # Ensure password is a string and log for debugging
    if not isinstance(password, str):
        password = str(password)
    
    logger.info(f"Creating user with email: {email}, password length: {len(password)}, password bytes: {len(password.encode('utf-8'))}")
    
    # Validate password length (bcrypt limit is 72 bytes)
    password_bytes = len(password.encode('utf-8'))
    if password_bytes > 72:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Password is too long (maximum 72 characters). Your password is {len(password)} characters."
        )
    
    if len(password) < 6:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Password must be at least 6 characters long"
        )
    
    with get_db() as conn:
        cursor = conn.cursor()
        
        # Check if user already exists
        cursor.execute("SELECT id FROM users WHERE email = ?", (email,))
        if cursor.fetchone():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Email already registered"
            )
        
        # Hash password and create user
        try:
            password_hash = hash_password(password)
        except Exception as e:
            import logging
            logger = logging.getLogger(__name__)
            logger.error(f"Error hashing password: {e}")
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Error processing password: {str(e)}"
            )
        cursor.execute("""
            INSERT INTO users (email, password_hash, name)
            VALUES (?, ?, ?)
        """, (email, password_hash, name))
        
        user_id = cursor.lastrowid
        cursor.execute("SELECT * FROM users WHERE id = ?", (user_id,))
        row = cursor.fetchone()
        
        return {
            "id": row["id"],
            "email": row["email"],
            "name": row["name"],
            "created_at": row["created_at"]
        }


def authenticate_user(email: str, password: str) -> Optional[Dict]:
    """Authenticate a user and return user data if successful."""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM users WHERE email = ?", (email,))
        row = cursor.fetchone()
        
        if not row:
            return None
        
        if not verify_password(password, row["password_hash"]):
            return None
        
        return {
            "id": row["id"],
            "email": row["email"],
            "name": row["name"],
            "created_at": row["created_at"]
        }


def create_access_token(data: Dict, expires_delta: Optional[timedelta] = None) -> str:
    """Create a JWT access token."""
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt


def verify_token(token: str) -> Dict:
    """Verify and decode a JWT token."""
    import logging
    logger = logging.getLogger(__name__)
    
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        return payload
    except jwt.ExpiredSignatureError as e:
        logger.error(f"Token expired: {e}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token has expired"
        )
    except jwt.JWTError as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials"
        )
    except Exception as e:
        import logging
        logger = logging.getLogger(__name__)
        logger.error(f"Unexpected error verifying token: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token verification failed"
        )


async def get_current_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security)
) -> Dict:
    """Get the current authenticated user from JWT token."""
    import logging
    logger = logging.getLogger(__name__)
    
    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    try:
        token = credentials.credentials
        payload = verify_token(token)
        user_id = payload.get("sub")
        
        if user_id is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Could not validate credentials"
            )
        
        # Convert user_id from string (JWT requirement) to int for database lookup
        if isinstance(user_id, str):
            try:
                user_id_int = int(user_id)
            except ValueError:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Invalid token format"
                )
        else:
            user_id_int = int(user_id)
        
        user_id = user_id_int  # Use integer for database query
        
        with get_db() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM users WHERE id = ?", (user_id,))
            row = cursor.fetchone()
            
            if not row:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="User not found"
                )
            
            return {
                "id": row["id"],
                "email": row["email"],
                "name": row["name"],
                "created_at": row["created_at"]
            }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in get_current_user: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Authentication error: {str(e)}"
        )


def get_user_by_id(user_id: int) -> Optional[Dict]:
    """Get a user by ID."""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM users WHERE id = ?", (user_id,))
        row = cursor.fetchone()
        
        if not row:
            return None
        
        return {
            "id": row["id"],
            "email": row["email"],
            "name": row["name"],
            "created_at": row["created_at"]
        }

