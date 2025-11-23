"""SQLite database for notification system."""

from __future__ import annotations

import sqlite3
import json
from pathlib import Path
from typing import Dict, List, Optional, Any
from datetime import datetime
from contextlib import contextmanager

DB_PATH = Path("data/notifications.db")
DB_PATH.parent.mkdir(parents=True, exist_ok=True)


@contextmanager
def get_db():
    """Context manager for database connections."""
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_db():
    """Initialize the database with required tables."""
    with get_db() as conn:
        cursor = conn.cursor()
        
        # SMTP Configuration table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS smtp_configs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                name TEXT NOT NULL,
                host TEXT NOT NULL,
                port INTEGER NOT NULL,
                username TEXT NOT NULL,
                password TEXT NOT NULL,
                use_tls BOOLEAN DEFAULT 1,
                from_email TEXT NOT NULL,
                from_name TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(user_id, name),
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
            )
        """)
        
        # ERP Tables: Workers
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS workers (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                name TEXT NOT NULL,
                email TEXT NOT NULL,
                phone TEXT,
                address TEXT,
                role TEXT,
                hourly_rate REAL,
                status TEXT DEFAULT 'active' CHECK(status IN ('active', 'inactive', 'terminated')),
                hire_date DATE,
                notes TEXT,
                smtp_config_id INTEGER,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
                FOREIGN KEY (smtp_config_id) REFERENCES smtp_configs(id)
            )
        """)
        
        # ERP Tables: Clients
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS clients (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                name TEXT NOT NULL,
                company_name TEXT,
                email TEXT NOT NULL,
                phone TEXT,
                address TEXT,
                contact_person TEXT,
                status TEXT DEFAULT 'active' CHECK(status IN ('active', 'inactive', 'completed')),
                notes TEXT,
                smtp_config_id INTEGER,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
                FOREIGN KEY (smtp_config_id) REFERENCES smtp_configs(id)
            )
        """)
        
        # ERP Tables: Vendors
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS vendors (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                name TEXT NOT NULL,
                company_name TEXT NOT NULL,
                email TEXT NOT NULL,
                phone TEXT,
                address TEXT,
                contact_person TEXT,
                vendor_type TEXT,
                payment_terms TEXT,
                status TEXT DEFAULT 'active' CHECK(status IN ('active', 'inactive', 'blacklisted')),
                notes TEXT,
                smtp_config_id INTEGER,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
                FOREIGN KEY (smtp_config_id) REFERENCES smtp_configs(id)
            )
        """)
        
        # ERP Tables: Payments
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS payments (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                payment_type TEXT NOT NULL CHECK(payment_type IN ('receive', 'send')),
                entity_type TEXT NOT NULL CHECK(entity_type IN ('client', 'vendor', 'worker')),
                entity_id INTEGER NOT NULL,
                amount REAL NOT NULL,
                currency TEXT DEFAULT 'USD',
                description TEXT,
                invoice_number TEXT,
                due_date DATE NOT NULL,
                status TEXT DEFAULT 'pending' CHECK(status IN ('pending', 'partial', 'paid', 'overdue', 'cancelled')),
                paid_amount REAL DEFAULT 0,
                paid_date DATE,
                payment_method TEXT,
                project_name TEXT,
                category TEXT,
                notes TEXT,
                payment_link TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
            )
        """)
        
        # Recipients table (vendors, workers, clients) - kept for backward compatibility
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS recipients (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                name TEXT NOT NULL,
                email TEXT NOT NULL,
                type TEXT NOT NULL CHECK(type IN ('vendor', 'worker', 'client')),
                phone TEXT,
                company TEXT,
                address TEXT,
                notes TEXT,
                smtp_config_id INTEGER,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
                FOREIGN KEY (smtp_config_id) REFERENCES smtp_configs(id)
            )
        """)
        
        # Enhanced Notification schedules table with date-based scheduling
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS notification_schedules (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                name TEXT NOT NULL,
                recipient_id INTEGER,
                payment_id INTEGER,
                notification_type TEXT NOT NULL CHECK(notification_type IN ('payment_reminder', 'payment_request', 'custom', 'due_date_reminder')),
                schedule_type TEXT DEFAULT 'interval' CHECK(schedule_type IN ('interval', 'date', 'before_due')),
                interval_days INTEGER,
                scheduled_date DATE,
                days_before_due INTEGER,
                enabled BOOLEAN DEFAULT 1,
                trigger_condition TEXT,
                email_template TEXT,
                payment_link TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                last_sent_at TIMESTAMP,
                next_send_at TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
                FOREIGN KEY (recipient_id) REFERENCES recipients(id),
                FOREIGN KEY (payment_id) REFERENCES payments(id)
            )
        """)
        
        # Notification history/logs
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS notification_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                schedule_id INTEGER,
                recipient_id INTEGER,
                payment_id INTEGER,
                notification_type TEXT NOT NULL,
                subject TEXT NOT NULL,
                body TEXT NOT NULL,
                status TEXT NOT NULL CHECK(status IN ('sent', 'failed', 'pending')),
                error_message TEXT,
                sent_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
                FOREIGN KEY (schedule_id) REFERENCES notification_schedules(id),
                FOREIGN KEY (recipient_id) REFERENCES recipients(id),
                FOREIGN KEY (payment_id) REFERENCES payments(id)
            )
        """)
        
        # Migrations: Add missing columns to existing tables
        try:
            # Check if payment_id column exists in notification_schedules
            cursor.execute("PRAGMA table_info(notification_schedules)")
            columns = [row[1] for row in cursor.fetchall()]
            if 'payment_id' not in columns:
                cursor.execute("ALTER TABLE notification_schedules ADD COLUMN payment_id INTEGER")
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_schedules_payment_id ON notification_schedules(payment_id)")
            if 'schedule_type' not in columns:
                cursor.execute("ALTER TABLE notification_schedules ADD COLUMN schedule_type TEXT DEFAULT 'interval'")
            if 'scheduled_date' not in columns:
                cursor.execute("ALTER TABLE notification_schedules ADD COLUMN scheduled_date DATE")
            if 'days_before_due' not in columns:
                cursor.execute("ALTER TABLE notification_schedules ADD COLUMN days_before_due INTEGER")
            if 'email_template' not in columns:
                cursor.execute("ALTER TABLE notification_schedules ADD COLUMN email_template TEXT")
            if 'payment_link' not in columns:
                cursor.execute("ALTER TABLE notification_schedules ADD COLUMN payment_link TEXT")
            # Add user_id if missing
            if 'user_id' not in columns:
                cursor.execute("ALTER TABLE notification_schedules ADD COLUMN user_id INTEGER DEFAULT 0")
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_schedules_user_id ON notification_schedules(user_id)")
        except sqlite3.OperationalError as e:
            # Column might already exist or table doesn't exist yet
            pass
        
        try:
            # Check if payment_id column exists in notification_history
            cursor.execute("PRAGMA table_info(notification_history)")
            columns = [row[1] for row in cursor.fetchall()]
            if 'payment_id' not in columns:
                cursor.execute("ALTER TABLE notification_history ADD COLUMN payment_id INTEGER")
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_history_payment_id ON notification_history(payment_id)")
            # Add user_id if missing
            if 'user_id' not in columns:
                cursor.execute("ALTER TABLE notification_history ADD COLUMN user_id INTEGER DEFAULT 0")
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_history_user_id ON notification_history(user_id)")
        except sqlite3.OperationalError as e:
            # Column might already exist or table doesn't exist yet
            pass
        
        try:
            # Check if payment_link column exists in payments table
            cursor.execute("PRAGMA table_info(payments)")
            columns = [row[1] for row in cursor.fetchall()]
            if 'payment_link' not in columns:
                cursor.execute("ALTER TABLE payments ADD COLUMN payment_link TEXT")
            if 'client_name' not in columns:
                cursor.execute("ALTER TABLE payments ADD COLUMN client_name TEXT")
            if 'client_email' not in columns:
                cursor.execute("ALTER TABLE payments ADD COLUMN client_email TEXT")
            # Add user_id if missing
            if 'user_id' not in columns:
                cursor.execute("ALTER TABLE payments ADD COLUMN user_id INTEGER DEFAULT 0")
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_payments_user_id ON payments(user_id)")
        except sqlite3.OperationalError as e:
            # Column might already exist or table doesn't exist yet
            pass
        
        # Add user_id to other tables if missing
        for table in ['smtp_configs', 'recipients', 'workers', 'clients', 'vendors']:
            try:
                cursor.execute(f"PRAGMA table_info({table})")
                columns = [row[1] for row in cursor.fetchall()]
                if 'user_id' not in columns:
                    cursor.execute(f"ALTER TABLE {table} ADD COLUMN user_id INTEGER DEFAULT 0")
                    cursor.execute(f"CREATE INDEX IF NOT EXISTS idx_{table}_user_id ON {table}(user_id)")
            except sqlite3.OperationalError:
                pass


def get_smtp_config(config_id: Optional[int] = None, name: Optional[str] = None, user_id: Optional[int] = None) -> Optional[Dict]:
    """Get SMTP configuration by ID or name."""
    with get_db() as conn:
        cursor = conn.cursor()
        if config_id:
            if user_id:
                cursor.execute("SELECT * FROM smtp_configs WHERE id = ? AND user_id = ?", (config_id, user_id))
            else:
                cursor.execute("SELECT * FROM smtp_configs WHERE id = ?", (config_id,))
        elif name:
            if user_id:
                cursor.execute("SELECT * FROM smtp_configs WHERE name = ? AND user_id = ?", (name, user_id))
            else:
                cursor.execute("SELECT * FROM smtp_configs WHERE name = ?", (name,))
        else:
            if user_id:
                cursor.execute("SELECT * FROM smtp_configs WHERE user_id = ? LIMIT 1", (user_id,))
            else:
                cursor.execute("SELECT * FROM smtp_configs LIMIT 1")
        
        row = cursor.fetchone()
        if row:
            return dict(row)
        return None


def create_smtp_config(data: Dict, user_id: int) -> int:
    """Create a new SMTP configuration."""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO smtp_configs (user_id, name, host, port, username, password, use_tls, from_email, from_name)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            user_id,
            data['name'],
            data['host'],
            data['port'],
            data['username'],
            data['password'],
            data.get('use_tls', True),
            data['from_email'],
            data.get('from_name', '')
        ))
        return cursor.lastrowid


def update_smtp_config(config_id: int, data: Dict, user_id: int) -> bool:
    """Update an existing SMTP configuration."""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            UPDATE smtp_configs 
            SET name = ?, host = ?, port = ?, username = ?, password = ?, 
                use_tls = ?, from_email = ?, from_name = ?, updated_at = CURRENT_TIMESTAMP
            WHERE id = ? AND user_id = ?
        """, (
            data['name'],
            data['host'],
            data['port'],
            data['username'],
            data['password'],
            data.get('use_tls', True),
            data['from_email'],
            data.get('from_name', ''),
            config_id,
            user_id
        ))
        return cursor.rowcount > 0


def list_smtp_configs(user_id: int) -> List[Dict]:
    """List all SMTP configurations for a user."""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM smtp_configs WHERE user_id = ? ORDER BY created_at DESC", (user_id,))
        return [dict(row) for row in cursor.fetchall()]


def delete_smtp_config(config_id: int, user_id: int) -> bool:
    """Delete an SMTP configuration."""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM smtp_configs WHERE id = ? AND user_id = ?", (config_id, user_id))
        return cursor.rowcount > 0


def create_recipient(data: Dict, user_id: int) -> int:
    """Create a new recipient."""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO recipients (user_id, name, email, type, phone, company, address, notes, smtp_config_id)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            user_id,
            data['name'],
            data['email'],
            data['type'],
            data.get('phone', ''),
            data.get('company', ''),
            data.get('address', ''),
            data.get('notes', ''),
            data.get('smtp_config_id')
        ))
        return cursor.lastrowid


def update_recipient(recipient_id: int, data: Dict, user_id: int) -> bool:
    """Update an existing recipient."""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            UPDATE recipients 
            SET name = ?, email = ?, type = ?, phone = ?, company = ?, 
                address = ?, notes = ?, smtp_config_id = ?, updated_at = CURRENT_TIMESTAMP
            WHERE id = ? AND user_id = ?
        """, (
            data['name'],
            data['email'],
            data['type'],
            data.get('phone', ''),
            data.get('company', ''),
            data.get('address', ''),
            data.get('notes', ''),
            data.get('smtp_config_id'),
            recipient_id,
            user_id
        ))
        return cursor.rowcount > 0


def get_recipient(recipient_id: int, user_id: int) -> Optional[Dict]:
    """Get a recipient by ID."""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM recipients WHERE id = ? AND user_id = ?", (recipient_id, user_id))
        row = cursor.fetchone()
        if row:
            return dict(row)
        return None


def list_recipients(user_id: int, recipient_type: Optional[str] = None) -> List[Dict]:
    """List all recipients, optionally filtered by type."""
    with get_db() as conn:
        cursor = conn.cursor()
        if recipient_type:
            cursor.execute("SELECT * FROM recipients WHERE user_id = ? AND type = ? ORDER BY name", (user_id, recipient_type))
        else:
            cursor.execute("SELECT * FROM recipients WHERE user_id = ? ORDER BY type, name", (user_id,))
        return [dict(row) for row in cursor.fetchall()]


def delete_recipient(recipient_id: int, user_id: int) -> bool:
    """Delete a recipient."""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM recipients WHERE id = ? AND user_id = ?", (recipient_id, user_id))
        return cursor.rowcount > 0


def create_schedule(data: Dict, user_id: int) -> int:
    """Create a new notification schedule."""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO notification_schedules 
            (user_id, name, recipient_id, payment_id, notification_type, schedule_type, interval_days, scheduled_date, 
             days_before_due, enabled, trigger_condition, email_template, payment_link)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            user_id,
            data['name'],
            data.get('recipient_id'),
            data.get('payment_id'),
            data['notification_type'],
            data.get('schedule_type', 'interval'),
            data.get('interval_days'),
            data.get('scheduled_date'),
            data.get('days_before_due'),
            data.get('enabled', True),
            data.get('trigger_condition', ''),
            data.get('email_template', ''),
            data.get('payment_link', '')
        ))
        return cursor.lastrowid


def update_schedule(schedule_id: int, data: Dict, user_id: int) -> bool:
    """Update an existing notification schedule."""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            UPDATE notification_schedules 
            SET name = ?, recipient_id = ?, payment_id = ?, notification_type = ?, schedule_type = ?,
                interval_days = ?, scheduled_date = ?, days_before_due = ?, enabled = ?, 
                trigger_condition = ?, email_template = ?, payment_link = ?, updated_at = CURRENT_TIMESTAMP
            WHERE id = ? AND user_id = ?
        """, (
            data['name'],
            data.get('recipient_id'),
            data.get('payment_id'),
            data['notification_type'],
            data.get('schedule_type', 'interval'),
            data.get('interval_days'),
            data.get('scheduled_date'),
            data.get('days_before_due'),
            data.get('enabled', True),
            data.get('trigger_condition', ''),
            data.get('email_template', ''),
            data.get('payment_link', ''),
            schedule_id,
            user_id
        ))
        return cursor.rowcount > 0


def get_schedule(schedule_id: int, user_id: int) -> Optional[Dict]:
    """Get a schedule by ID."""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM notification_schedules WHERE id = ? AND user_id = ?", (schedule_id, user_id))
        row = cursor.fetchone()
        if row:
            return dict(row)
        return None


def list_schedules(user_id: int, enabled_only: bool = False) -> List[Dict]:
    """List all notification schedules."""
    with get_db() as conn:
        cursor = conn.cursor()
        if enabled_only:
            cursor.execute("SELECT * FROM notification_schedules WHERE user_id = ? AND enabled = 1 ORDER BY name", (user_id,))
        else:
            cursor.execute("SELECT * FROM notification_schedules WHERE user_id = ? ORDER BY name", (user_id,))
        return [dict(row) for row in cursor.fetchall()]


def delete_schedule(schedule_id: int, user_id: int) -> bool:
    """Delete a notification schedule."""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM notification_schedules WHERE id = ? AND user_id = ?", (schedule_id, user_id))
        return cursor.rowcount > 0


def update_schedule_sent_time(schedule_id: int, next_send_at: Optional[datetime] = None):
    """Update the last sent time and next send time for a schedule."""
    with get_db() as conn:
        cursor = conn.cursor()
        if next_send_at:
            cursor.execute("""
                UPDATE notification_schedules 
                SET last_sent_at = CURRENT_TIMESTAMP, next_send_at = ?
                WHERE id = ?
            """, (next_send_at.isoformat(), schedule_id))
        else:
            cursor.execute("""
                UPDATE notification_schedules 
                SET last_sent_at = CURRENT_TIMESTAMP
                WHERE id = ?
            """, (schedule_id,))


def log_notification(data: Dict, user_id: int) -> int:
    """Log a notification in history."""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO notification_history 
            (user_id, schedule_id, recipient_id, notification_type, subject, body, status, error_message)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            user_id,
            data.get('schedule_id'),
            data['recipient_id'],
            data['notification_type'],
            data['subject'],
            data['body'],
            data['status'],
            data.get('error_message')
        ))
        return cursor.lastrowid


def get_notification_history(user_id: int, limit: int = 100, recipient_id: Optional[int] = None) -> List[Dict]:
    """Get notification history."""
    with get_db() as conn:
        cursor = conn.cursor()
        if recipient_id:
            cursor.execute("""
                SELECT * FROM notification_history 
                WHERE user_id = ? AND recipient_id = ? 
                ORDER BY sent_at DESC 
                LIMIT ?
            """, (user_id, recipient_id, limit))
        else:
            cursor.execute("""
                SELECT * FROM notification_history 
                WHERE user_id = ? 
                ORDER BY sent_at DESC 
                LIMIT ?
            """, (user_id, limit))
        return [dict(row) for row in cursor.fetchall()]


# ==================== ERP TABLE FUNCTIONS ====================

# Workers CRUD
def create_worker(data: Dict) -> int:
    """Create a new worker."""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO workers (name, email, phone, address, role, hourly_rate, status, hire_date, notes, smtp_config_id)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            data['name'],
            data['email'],
            data.get('phone', ''),
            data.get('address', ''),
            data.get('role', ''),
            data.get('hourly_rate', 0),
            data.get('status', 'active'),
            data.get('hire_date'),
            data.get('notes', ''),
            data.get('smtp_config_id')
        ))
        return cursor.lastrowid


def update_worker(worker_id: int, data: Dict) -> bool:
    """Update a worker."""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            UPDATE workers 
            SET name = ?, email = ?, phone = ?, address = ?, role = ?, hourly_rate = ?,
                status = ?, hire_date = ?, notes = ?, smtp_config_id = ?, updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
        """, (
            data['name'],
            data['email'],
            data.get('phone', ''),
            data.get('address', ''),
            data.get('role', ''),
            data.get('hourly_rate', 0),
            data.get('status', 'active'),
            data.get('hire_date'),
            data.get('notes', ''),
            data.get('smtp_config_id'),
            worker_id
        ))
        return cursor.rowcount > 0


def get_worker(worker_id: int) -> Optional[Dict]:
    """Get a worker by ID."""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM workers WHERE id = ?", (worker_id,))
        row = cursor.fetchone()
        if row:
            return dict(row)
        return None


def list_workers(status: Optional[str] = None) -> List[Dict]:
    """List all workers."""
    with get_db() as conn:
        cursor = conn.cursor()
        if status:
            cursor.execute("SELECT * FROM workers WHERE status = ? ORDER BY name", (status,))
        else:
            cursor.execute("SELECT * FROM workers ORDER BY name")
        return [dict(row) for row in cursor.fetchall()]


def delete_worker(worker_id: int) -> bool:
    """Delete a worker."""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM workers WHERE id = ?", (worker_id,))
        return cursor.rowcount > 0


# Clients CRUD
def create_client(data: Dict) -> int:
    """Create a new client."""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO clients (name, company_name, email, phone, address, contact_person, status, notes, smtp_config_id)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            data['name'],
            data.get('company_name', ''),
            data['email'],
            data.get('phone', ''),
            data.get('address', ''),
            data.get('contact_person', ''),
            data.get('status', 'active'),
            data.get('notes', ''),
            data.get('smtp_config_id')
        ))
        return cursor.lastrowid


def update_client(client_id: int, data: Dict) -> bool:
    """Update a client."""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            UPDATE clients 
            SET name = ?, company_name = ?, email = ?, phone = ?, address = ?,
                contact_person = ?, status = ?, notes = ?, smtp_config_id = ?, updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
        """, (
            data['name'],
            data.get('company_name', ''),
            data['email'],
            data.get('phone', ''),
            data.get('address', ''),
            data.get('contact_person', ''),
            data.get('status', 'active'),
            data.get('notes', ''),
            data.get('smtp_config_id'),
            client_id
        ))
        return cursor.rowcount > 0


def get_client(client_id: int) -> Optional[Dict]:
    """Get a client by ID."""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM clients WHERE id = ?", (client_id,))
        row = cursor.fetchone()
        if row:
            return dict(row)
        return None


def list_clients(status: Optional[str] = None) -> List[Dict]:
    """List all clients."""
    with get_db() as conn:
        cursor = conn.cursor()
        if status:
            cursor.execute("SELECT * FROM clients WHERE status = ? ORDER BY name", (status,))
        else:
            cursor.execute("SELECT * FROM clients ORDER BY name")
        return [dict(row) for row in cursor.fetchall()]


def delete_client(client_id: int) -> bool:
    """Delete a client."""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM clients WHERE id = ?", (client_id,))
        return cursor.rowcount > 0


# Vendors CRUD
def create_vendor(data: Dict) -> int:
    """Create a new vendor."""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO vendors (name, company_name, email, phone, address, contact_person, vendor_type, payment_terms, status, notes, smtp_config_id)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            data['name'],
            data['company_name'],
            data['email'],
            data.get('phone', ''),
            data.get('address', ''),
            data.get('contact_person', ''),
            data.get('vendor_type', ''),
            data.get('payment_terms', ''),
            data.get('status', 'active'),
            data.get('notes', ''),
            data.get('smtp_config_id')
        ))
        return cursor.lastrowid


def update_vendor(vendor_id: int, data: Dict) -> bool:
    """Update a vendor."""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            UPDATE vendors 
            SET name = ?, company_name = ?, email = ?, phone = ?, address = ?,
                contact_person = ?, vendor_type = ?, payment_terms = ?, status = ?, notes = ?, smtp_config_id = ?, updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
        """, (
            data['name'],
            data['company_name'],
            data['email'],
            data.get('phone', ''),
            data.get('address', ''),
            data.get('contact_person', ''),
            data.get('vendor_type', ''),
            data.get('payment_terms', ''),
            data.get('status', 'active'),
            data.get('notes', ''),
            data.get('smtp_config_id'),
            vendor_id
        ))
        return cursor.rowcount > 0


def get_vendor(vendor_id: int) -> Optional[Dict]:
    """Get a vendor by ID."""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM vendors WHERE id = ?", (vendor_id,))
        row = cursor.fetchone()
        if row:
            return dict(row)
        return None


def list_vendors(status: Optional[str] = None) -> List[Dict]:
    """List all vendors."""
    with get_db() as conn:
        cursor = conn.cursor()
        if status:
            cursor.execute("SELECT * FROM vendors WHERE status = ? ORDER BY name", (status,))
        else:
            cursor.execute("SELECT * FROM vendors ORDER BY name")
        return [dict(row) for row in cursor.fetchall()]


def delete_vendor(vendor_id: int) -> bool:
    """Delete a vendor."""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM vendors WHERE id = ?", (vendor_id,))
        return cursor.rowcount > 0


# Payments CRUD
def create_payment(data: Dict, user_id: int) -> int:
    """Create a new payment record."""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO payments (user_id, payment_type, entity_type, entity_id, amount, currency, description, invoice_number, 
                                due_date, status, paid_amount, paid_date, payment_method, project_name, category, notes, 
                                payment_link, client_name, client_email)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            user_id,
            data['payment_type'],
            data.get('entity_type', 'client'),
            data.get('entity_id', 0),
            data['amount'],
            data.get('currency', 'USD'),
            data.get('description', ''),
            data.get('invoice_number', ''),
            data['due_date'],
            data.get('status', 'pending'),
            data.get('paid_amount', 0),
            data.get('paid_date'),
            data.get('payment_method', ''),
            data.get('project_name', ''),
            data.get('category', ''),
            data.get('notes', ''),
            data.get('payment_link', ''),
            data.get('client_name', ''),
            data.get('client_email', '')
        ))
        return cursor.lastrowid


def update_payment(payment_id: int, data: Dict, user_id: int) -> bool:
    """Update a payment record."""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            UPDATE payments 
            SET payment_type = ?, entity_type = ?, entity_id = ?, amount = ?, currency = ?, description = ?,
                invoice_number = ?, due_date = ?, status = ?, paid_amount = ?, paid_date = ?, payment_method = ?,
                project_name = ?, category = ?, notes = ?, payment_link = ?, client_name = ?, client_email = ?, 
                updated_at = CURRENT_TIMESTAMP
            WHERE id = ? AND user_id = ?
        """, (
            data['payment_type'],
            data.get('entity_type', 'client'),
            data.get('entity_id', 0),
            data['amount'],
            data.get('currency', 'USD'),
            data.get('description', ''),
            data.get('invoice_number', ''),
            data['due_date'],
            data.get('status', 'pending'),
            data.get('paid_amount', 0),
            data.get('paid_date'),
            data.get('payment_method', ''),
            data.get('project_name', ''),
            data.get('category', ''),
            data.get('notes', ''),
            data.get('payment_link', ''),
            data.get('client_name', ''),
            data.get('client_email', ''),
            payment_id,
            user_id
        ))
        return cursor.rowcount > 0


def get_payment(payment_id: int, user_id: int) -> Optional[Dict]:
    """Get a payment by ID."""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM payments WHERE id = ? AND user_id = ?", (payment_id, user_id))
        row = cursor.fetchone()
        if row:
            return dict(row)
        return None


def list_payments(
    user_id: int,
    payment_type: Optional[str] = None,
    entity_type: Optional[str] = None,
    status: Optional[str] = None,
    limit: Optional[int] = None
) -> List[Dict]:
    """List all payments with optional filters."""
    with get_db() as conn:
        cursor = conn.cursor()
        conditions = ["user_id = ?"]
        params = [user_id]
        
        if payment_type:
            conditions.append("payment_type = ?")
            params.append(payment_type)
        if entity_type:
            conditions.append("entity_type = ?")
            params.append(entity_type)
        if status:
            conditions.append("status = ?")
            params.append(status)
        
        where_clause = " WHERE " + " AND ".join(conditions)
        limit_clause = f" LIMIT {limit}" if limit else ""
        
        query = f"SELECT * FROM payments{where_clause} ORDER BY due_date DESC{limit_clause}"
        cursor.execute(query, params)
        return [dict(row) for row in cursor.fetchall()]


def get_payments_due_soon(user_id: int, days: int = 7) -> List[Dict]:
    """Get payments due within specified days."""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT * FROM payments 
            WHERE user_id = ? AND status IN ('pending', 'partial')
            AND due_date <= date('now', '+' || ? || ' days')
            AND due_date >= date('now')
            ORDER BY due_date ASC
        """, (user_id, days))
        return [dict(row) for row in cursor.fetchall()]


def get_overdue_payments(user_id: int) -> List[Dict]:
    """Get all overdue payments."""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT * FROM payments 
            WHERE user_id = ? AND status IN ('pending', 'partial')
            AND due_date < date('now')
            ORDER BY due_date ASC
        """, (user_id,))
        return [dict(row) for row in cursor.fetchall()]


def delete_payment(payment_id: int, user_id: int) -> bool:
    """Delete a payment record."""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM payments WHERE id = ? AND user_id = ?", (payment_id, user_id))
        return cursor.rowcount > 0


# Initialize database on import (users table will be initialized by auth module)
# Note: init_db() should be called after auth.init_auth_db() to ensure users table exists first
# For now, we'll call it here but it will handle missing users table gracefully
try:
    init_db()
except sqlite3.OperationalError:
    # Users table might not exist yet, that's okay
    pass

