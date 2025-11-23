"""Notification service for sending emails with AI-generated content."""

from __future__ import annotations

import smtplib
import logging
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime, timedelta
from typing import Dict, Optional, List, Any
from pathlib import Path

from langchain_openai import ChatOpenAI
from langchain_core.prompts import ChatPromptTemplate

from .notifications_db import (
    get_smtp_config, get_recipient, get_schedule, list_schedules,
    update_schedule_sent_time, log_notification, get_notification_history
)

logger = logging.getLogger(__name__)


class NotificationService:
    """Service for sending notifications via email."""
    
    def __init__(self, llm: Optional[ChatOpenAI] = None):
        """Initialize the notification service."""
        self.llm = llm or ChatOpenAI(
            model="gpt-4o-mini",
            temperature=0.7,
        )
    
    def _generate_email_content(
        self,
        notification_type: str,
        recipient: Dict,
        context: Optional[Dict] = None,
        template: Optional[str] = None,
        payment_link: Optional[str] = None,
        sender_name: Optional[str] = None
    ) -> tuple[str, str]:
        """Generate email subject and body using AI."""
        
        recipient_name = recipient.get('name', '')
        recipient_type = recipient.get('type', '')
        sender_name_display = sender_name or "ConstructionBot Team"
        
        if template:
            # Use custom template if provided - replace placeholders first
            template_filled = template
            if context:
                template_filled = template_filled.replace('{amount}', str(context.get('payment_amount', '')))
                template_filled = template_filled.replace('{due_date}', str(context.get('due_date', '')))
                template_filled = template_filled.replace('{invoice_number}', str(context.get('invoice_number', '')))
                template_filled = template_filled.replace('{project_name}', str(context.get('project_name', '')))
                template_filled = template_filled.replace('{description}', str(context.get('description', '')))
                template_filled = template_filled.replace('{recipient_name}', recipient_name)
            
            # Replace sender placeholders in template
            if sender_name:
                template_filled = template_filled.replace('{sender_name}', sender_name)
                template_filled = template_filled.replace('{sender}', sender_name)
                template_filled = template_filled.replace('{from_name}', sender_name)
            
            prompt = ChatPromptTemplate.from_messages([
                ("system", "You are a professional email writer for construction business communications. "
                 "Generate a professional email based on the provided template and context. "
                 "Use the template as a guide but make it natural and professional. "
                 "Replace any remaining placeholders with actual values from the context. "
                 "Always end with 'Best Regards,' followed by the sender's name."),
                ("human", """Generate an email with subject and body based on this template:

Template:
{template}

Recipient Information:
- Name: {recipient_name}
- Type: {recipient_type}
- Company: {company}

Sender: {sender_name}

Context:
{context}

Payment Link: {payment_link}

Generate a professional email with:
1. Subject line
2. Email body (end with "Best Regards," followed by the sender's name: {sender_name})

Format your response as:
SUBJECT: [subject line]
BODY: [email body]""")
            ])
            
            # Format context nicely for the prompt
            context_details = []
            if context:
                if context.get('payment_amount'):
                    context_details.append(f"Payment Amount: ${float(context.get('payment_amount', 0)):,.2f}")
                if context.get('due_date'):
                    context_details.append(f"Due Date: {context.get('due_date')}")
                if context.get('invoice_number'):
                    context_details.append(f"Invoice Number: {context.get('invoice_number')}")
                if context.get('project_name'):
                    context_details.append(f"Project Name: {context.get('project_name')}")
                if context.get('description'):
                    context_details.append(f"Description: {context.get('description')}")
            
            context_str = '\n'.join(context_details) if context_details else (str(context) if context else "No additional context provided.")
            company = recipient.get('company', '')
            
            response = self.llm.invoke(prompt.format_messages(
                template=template_filled,
                recipient_name=recipient_name,
                recipient_type=recipient_type,
                company=company,
                context=context_str,
                payment_link=payment_link or 'Not provided',
                sender_name=sender_name_display
            ))
            
            content = response.content
            
            # Parse subject and body
            lines = content.split('\n')
            subject = ''
            body_lines = []
            in_body = False
            
            for line in lines:
                if line.strip().startswith('SUBJECT:'):
                    subject = line.replace('SUBJECT:', '').strip()
                elif line.strip().startswith('BODY:'):
                    in_body = True
                    body = line.replace('BODY:', '').strip()
                    if body:
                        body_lines.append(body)
                elif in_body:
                    body_lines.append(line)
            
            if not subject:
                subject = f"Notification from ConstructionBot - {notification_type.replace('_', ' ').title()}"
            
            body = '\n'.join(body_lines).strip()
            if not body:
                body = content
            
            # Replace any remaining placeholders with actual values from context
            if context:
                # Replace common placeholder patterns
                amount = context.get('payment_amount') or context.get('amount')
                if amount:
                    amount_str = f"${float(amount):,.2f}" if isinstance(amount, (int, float)) else str(amount)
                    body = body.replace('[Please insert the amount]', amount_str)
                    body = body.replace('[amount]', amount_str)
                    body = body.replace('{amount}', amount_str)
                
                due_date = context.get('due_date')
                if due_date:
                    body = body.replace('[Please insert the due date]', str(due_date))
                    body = body.replace('[due date]', str(due_date))
                    body = body.replace('{due_date}', str(due_date))
                
                invoice_number = context.get('invoice_number')
                if invoice_number:
                    body = body.replace('[Please insert the invoice number]', str(invoice_number))
                    body = body.replace('[invoice number]', str(invoice_number))
                    body = body.replace('{invoice_number}', str(invoice_number))
                
                project_name = context.get('project_name')
                if project_name:
                    body = body.replace('[Please insert the project name]', str(project_name))
                    body = body.replace('[project name]', str(project_name))
                    body = body.replace('{project_name}', str(project_name))
                
                description = context.get('description')
                if description:
                    body = body.replace('[Please insert the description]', str(description))
                    body = body.replace('[description]', str(description))
                    body = body.replace('{description}', str(description))
            
            # Replace payment link placeholder
            if payment_link:
                body = body.replace('[Payment Link]', payment_link)
                body = body.replace('{payment_link}', payment_link)
            
            # Replace any remaining sender placeholders in the body
            if sender_name:
                body = body.replace('{sender_name}', sender_name)
                body = body.replace('{sender}', sender_name)
                body = body.replace('{from_name}', sender_name)
                body = body.replace('[Sender Name]', sender_name)
                body = body.replace('[Your Name]', sender_name)
            
            # Replace recipient name placeholders
            body = body.replace('{recipient_name}', recipient_name)
            body = body.replace('[Recipient Name]', recipient_name)
            
            return subject, body
        
        # Generate based on notification type (if no template provided)
        sender_name_display = sender_name or "ConstructionBot Team"
        
        # Format context nicely for the prompt
        context_details = []
        if context:
            if context.get('payment_amount'):
                context_details.append(f"Payment Amount: ${float(context.get('payment_amount', 0)):,.2f}")
            if context.get('due_date'):
                context_details.append(f"Due Date: {context.get('due_date')}")
            if context.get('invoice_number'):
                context_details.append(f"Invoice Number: {context.get('invoice_number')}")
            if context.get('project_name'):
                context_details.append(f"Project Name: {context.get('project_name')}")
            if context.get('description'):
                context_details.append(f"Description: {context.get('description')}")
        
        context_str = '\n'.join(context_details) if context_details else (str(context) if context else "No additional context provided.")
        
        if notification_type == 'payment_reminder':
            prompt = ChatPromptTemplate.from_messages([
                ("system", "You are a professional email writer for construction business communications."),
                ("human", """Write a professional payment reminder email.

Recipient: {recipient_name} ({recipient_type})
Company: {company}
Sender: {sender_name}

Payment Details:
{context}

Payment Link: {payment_link}

The email should:
- Be professional and courteous
- Clearly state the payment amount (if available)
- Clearly state the due date (if available)
- Include invoice number if available
- Include project name if available
- Include description if available
- Include the payment link if provided
- End with "Best Regards," followed by the sender's name: {sender_name}
- Be concise but complete
- Make sure to include ALL payment details from the context above

Format your response as:
SUBJECT: [subject line]
BODY: [email body]""")
            ])
        elif notification_type == 'payment_request':
            prompt = ChatPromptTemplate.from_messages([
                ("system", "You are a professional email writer for construction business communications."),
                ("human", """Write a professional payment request email to a client.

Recipient: {recipient_name} (client)
Company: {company}
Sender: {sender_name}

Payment Details:
{context}

Payment Link: {payment_link}

The email should:
- Be professional and clear
- Clearly state the payment amount (if available)
- Clearly state the due date (if available)
- Include invoice number if available
- Include project name if available
- Include description if available
- Include the payment link
- Request payment politely but firmly
- Include payment instructions
- End with "Best Regards," followed by the sender's name: {sender_name}
- Make sure to include ALL payment details from the context above

Format your response as:
SUBJECT: [subject line]
BODY: [email body]""")
            ])
        else:  # custom
            prompt = ChatPromptTemplate.from_messages([
                ("system", "You are a professional email writer for construction business communications."),
                ("human", """Write a professional email.

Recipient: {recipient_name} ({recipient_type})
Company: {company}
Sender: {sender_name}

Payment Details:
{context}

Payment Link: {payment_link}

The email should:
- Include ALL payment details from the context above (amount, due date, invoice number, project name, description)
- Include the payment link
- End with "Best Regards," followed by the sender's name: {sender_name}
- Make sure to include ALL payment details from the context above

Format your response as:
SUBJECT: [subject line]
BODY: [email body]""")
            ])
        
        company = recipient.get('company', '')
        
        response = self.llm.invoke(prompt.format_messages(
            template=template or '',
            recipient_name=recipient_name,
            recipient_type=recipient_type,
            company=company,
            context=context_str,
            payment_link=payment_link or 'Not provided',
            sender_name=sender_name_display
        ))
        
        content = response.content
        
        # Parse subject and body
        lines = content.split('\n')
        subject = ''
        body_lines = []
        in_body = False
        
        for line in lines:
            if line.strip().startswith('SUBJECT:'):
                subject = line.replace('SUBJECT:', '').strip()
            elif line.strip().startswith('BODY:'):
                in_body = True
                body = line.replace('BODY:', '').strip()
                if body:
                    body_lines.append(body)
            elif in_body:
                body_lines.append(line)
        
        if not subject:
            subject = f"Notification from ConstructionBot - {notification_type.replace('_', ' ').title()}"
        
        body = '\n'.join(body_lines).strip()
        if not body:
            body = content
        
        # Replace any remaining placeholders with actual values from context
        if context:
            # Replace common placeholder patterns
            amount = context.get('payment_amount') or context.get('amount')
            if amount:
                amount_str = f"${float(amount):,.2f}" if isinstance(amount, (int, float)) else str(amount)
                body = body.replace('[Please insert the amount]', amount_str)
                body = body.replace('[amount]', amount_str)
                body = body.replace('{amount}', amount_str)
            
            due_date = context.get('due_date')
            if due_date:
                body = body.replace('[Please insert the due date]', str(due_date))
                body = body.replace('[due date]', str(due_date))
                body = body.replace('{due_date}', str(due_date))
            
            invoice_number = context.get('invoice_number')
            if invoice_number:
                body = body.replace('[Please insert the invoice number]', str(invoice_number))
                body = body.replace('[invoice number]', str(invoice_number))
                body = body.replace('{invoice_number}', str(invoice_number))
            
            project_name = context.get('project_name')
            if project_name:
                body = body.replace('[Please insert the project name]', str(project_name))
                body = body.replace('[project name]', str(project_name))
                body = body.replace('{project_name}', str(project_name))
            
            description = context.get('description')
            if description:
                body = body.replace('[Please insert the description]', str(description))
                body = body.replace('[description]', str(description))
                body = body.replace('{description}', str(description))
        
        # Replace payment link placeholder
        if payment_link:
            body = body.replace('[Payment Link]', payment_link)
            body = body.replace('{payment_link}', payment_link)
        
        # Replace any remaining sender placeholders in the body
        if sender_name:
            body = body.replace('{sender_name}', sender_name)
            body = body.replace('{sender}', sender_name)
            body = body.replace('{from_name}', sender_name)
            body = body.replace('[Sender Name]', sender_name)
            body = body.replace('[Your Name]', sender_name)
        
        # Replace recipient name placeholders
        body = body.replace('{recipient_name}', recipient_name)
        body = body.replace('[Recipient Name]', recipient_name)
        
        return subject, body
    
    def _send_email(
        self,
        smtp_config: Dict,
        to_email: str,
        subject: str,
        body: str,
        from_name: Optional[str] = None
    ) -> bool:
        """Send an email using SMTP configuration."""
        logger.info("=" * 80)
        logger.info("📧 STARTING EMAIL SEND PROCESS")
        logger.info("=" * 80)
        
        try:
            # Log configuration (mask password)
            masked_password = "*" * len(smtp_config['password']) if smtp_config.get('password') else "NOT SET"
            logger.info(f"📋 SMTP Configuration:")
            logger.info(f"   Host: {smtp_config.get('host', 'NOT SET')}")
            logger.info(f"   Port: {smtp_config.get('port', 'NOT SET')}")
            logger.info(f"   Username: {smtp_config.get('username', 'NOT SET')}")
            logger.info(f"   Password: {masked_password} (length: {len(smtp_config.get('password', ''))})")
            logger.info(f"   Use TLS: {smtp_config.get('use_tls', True)}")
            logger.info(f"   From Email: {smtp_config.get('from_email', 'NOT SET')}")
            logger.info(f"   From Name: {smtp_config.get('from_name', 'NOT SET')}")
            logger.info(f"   To Email: {to_email}")
            logger.info(f"   Subject: {subject}")
            logger.info(f"   Body Length: {len(body)} characters")
            
            logger.info("")
            logger.info("📝 Step 1: Creating email message...")
            msg = MIMEMultipart()
            from_address = f"{from_name or smtp_config.get('from_name', '')} <{smtp_config['from_email']}>"
            msg['From'] = from_address
            msg['To'] = to_email
            msg['Subject'] = subject
            logger.info(f"   ✓ From: {from_address}")
            logger.info(f"   ✓ To: {to_email}")
            logger.info(f"   ✓ Subject: {subject}")
            
            logger.info("")
            logger.info("📎 Step 2: Attaching email body...")
            msg.attach(MIMEText(body, 'plain'))
            logger.info(f"   ✓ Body attached ({len(body)} chars)")
            
            logger.info("")
            logger.info(f"🔌 Step 3: Connecting to SMTP server {smtp_config['host']}:{smtp_config['port']}...")
            server = smtplib.SMTP(smtp_config['host'], smtp_config['port'])
            logger.info("   ✓ SMTP connection established")
            
            if smtp_config.get('use_tls', True):
                logger.info("")
                logger.info("🔒 Step 4: Starting TLS encryption...")
                server.starttls()
                logger.info("   ✓ TLS started successfully")
            else:
                logger.info("")
                logger.info("⚠️  Step 4: Skipping TLS (use_tls=False)")
            
            logger.info("")
            logger.info(f"🔐 Step 5: Authenticating with username: {smtp_config['username']}, smtp_config['password'] is {smtp_config['password']}")
            server.login(smtp_config['username'], smtp_config['password'])
            logger.info("   ✓ Authentication successful")
            
            logger.info("")
            logger.info("📤 Step 6: Sending email message...")
            server.send_message(msg)
            logger.info("   ✓ Email sent successfully")
            
            logger.info("")
            logger.info("🔌 Step 7: Closing SMTP connection...")
            server.quit()
            logger.info("   ✓ Connection closed")
            
            logger.info("")
            logger.info("=" * 80)
            logger.info("✅ EMAIL SEND SUCCESSFUL")
            logger.info("=" * 80)
            
            return True
        except smtplib.SMTPConnectError as e:
            logger.error("=" * 80)
            logger.error("❌ EMAIL SEND FAILED - CONNECTION ERROR")
            logger.error("=" * 80)
            logger.error(f"Error Type: SMTPConnectError")
            logger.error(f"Error Message: {str(e)}")
            logger.error(f"SMTP Host: {smtp_config.get('host', 'NOT SET')}")
            logger.error(f"SMTP Port: {smtp_config.get('port', 'NOT SET')}")
            logger.error("Possible causes:")
            logger.error("  - Wrong SMTP host or port")
            logger.error("  - Firewall blocking connection")
            logger.error("  - Network connectivity issues")
            logger.error("  - SMTP server is down")
            logger.error("=" * 80)
            return False
        except smtplib.SMTPAuthenticationError as e:
            logger.error("=" * 80)
            logger.error("❌ EMAIL SEND FAILED - AUTHENTICATION ERROR")
            logger.error("=" * 80)
            logger.error(f"Error Type: SMTPAuthenticationError")
            logger.error(f"Error Message: {str(e)}")
            logger.error(f"Username: {smtp_config.get('username', 'NOT SET')}")
            logger.error(f"Password Length: {len(smtp_config.get('password', ''))}")
            logger.error("Possible causes:")
            logger.error("  - Wrong username or password")
            logger.error("  - Account requires app-specific password (Gmail)")
            logger.error("  - Account has 2FA enabled without app password")
            logger.error("=" * 80)
            return False
        except smtplib.SMTPException as e:
            logger.error("=" * 80)
            logger.error("❌ EMAIL SEND FAILED - SMTP ERROR")
            logger.error("=" * 80)
            logger.error(f"Error Type: SMTPException")
            logger.error(f"Error Message: {str(e)}")
            logger.error(f"SMTP Host: {smtp_config.get('host', 'NOT SET')}")
            logger.error(f"SMTP Port: {smtp_config.get('port', 'NOT SET')}")
            logger.error("=" * 80)
            return False
        except Exception as e:
            logger.error("=" * 80)
            logger.error("❌ EMAIL SEND FAILED - UNEXPECTED ERROR")
            logger.error("=" * 80)
            logger.error(f"Error Type: {type(e).__name__}")
            logger.error(f"Error Message: {str(e)}")
            logger.error(f"Full Traceback:")
            import traceback
            logger.error(traceback.format_exc())
            logger.error("=" * 80)
            return False
    
    def send_notification(
        self,
        schedule_id: int,
        user_id: int,
        context: Optional[Dict] = None,
        force: bool = False
    ) -> Dict:
        """Send a notification based on a schedule."""
        logger.info("")
        logger.info("🚀 STARTING NOTIFICATION SEND (Schedule-based)")
        logger.info(f"   Schedule ID: {schedule_id}")
        logger.info(f"   User ID: {user_id}")
        logger.info(f"   Force: {force}")
        logger.info(f"   Context: {context}")
        
        schedule = get_schedule(schedule_id, user_id=user_id)
        if not schedule:
            logger.error("   ❌ Schedule not found")
            return {"success": False, "error": "Schedule not found"}
        logger.info(f"   ✓ Schedule found: {schedule.get('name', 'Unnamed')}")
        
        if not schedule.get('enabled') and not force:
            logger.warning("   ⚠️  Schedule is disabled and force=False")
            return {"success": False, "error": "Schedule is disabled"}
        
        recipient = get_recipient(schedule['recipient_id'], user_id=user_id)
        if not recipient:
            logger.error(f"   ❌ Recipient not found (ID: {schedule['recipient_id']})")
            return {"success": False, "error": "Recipient not found"}
        logger.info(f"   ✓ Recipient found: {recipient.get('name', 'Unnamed')} ({recipient.get('email', 'No email')})")
        
        # Get payment info if payment_id exists
        payment = None
        payment_id = schedule.get('payment_id')
        if payment_id:
            from .notifications_db import get_payment
            payment = get_payment(payment_id)
            if payment:
                logger.info(f"   ✓ Payment found: ${payment.get('amount', 0)} due {payment.get('due_date', 'N/A')}")
                # Update context with payment info
                if not context:
                    context = {}
                context.update({
                    'payment_amount': payment.get('amount', 0),
                    'due_date': payment.get('due_date', ''),
                    'invoice_number': payment.get('invoice_number', ''),
                    'project_name': payment.get('project_name', ''),
                    'description': payment.get('description', '')
                })
        
        # Get SMTP config
        smtp_config_id = recipient.get('smtp_config_id') or schedule.get('smtp_config_id')
        logger.info(f"   Looking for SMTP config (ID: {smtp_config_id})...")
        if not smtp_config_id:
            logger.info("   No SMTP config ID specified, trying to get default...")
            smtp_config = get_smtp_config(user_id=user_id)
        else:
            smtp_config = get_smtp_config(config_id=smtp_config_id, user_id=user_id)
        
        if not smtp_config:
            logger.error("   ❌ SMTP configuration not found")
            return {"success": False, "error": "SMTP configuration not found"}
        logger.info(f"   ✓ SMTP config found: {smtp_config.get('name', 'Unnamed')}")
        
        # Generate email content
        logger.info("")
        logger.info("🤖 Generating email content with AI...")
        try:
            subject, body = self._generate_email_content(
                notification_type=schedule['notification_type'],
                recipient=recipient,
                context=context,
                template=schedule.get('email_template'),
                payment_link=schedule.get('payment_link') or (payment.get('payment_link', '') if payment else ''),
                sender_name=smtp_config.get('from_name', '')
            )
            logger.info(f"   ✓ Email content generated")
            logger.info(f"   Subject: {subject}")
            logger.info(f"   Body preview: {body[:100]}...")
        except Exception as e:
            logger.error(f"   ❌ Failed to generate email content: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return {"success": False, "error": f"Failed to generate email: {str(e)}"}
        
        # Send email
        logger.info("")
        success = self._send_email(
            smtp_config=smtp_config,
            to_email=recipient['email'],
            subject=subject,
            body=body,
            from_name=smtp_config.get('from_name')
        )
        
        # Log notification
        logger.info("")
        logger.info("📝 Logging notification to database...")
        log_notification({
            'schedule_id': schedule_id,
            'recipient_id': recipient['id'],
            'notification_type': schedule['notification_type'],
            'subject': subject,
            'body': body,
            'status': 'sent' if success else 'failed',
            'error_message': None if success else "SMTP send failed"
        }, user_id=user_id)
        logger.info(f"   ✓ Notification logged (status: {'sent' if success else 'failed'})")
        
        # Update schedule sent time
        if success:
            schedule_type = schedule.get('schedule_type', 'interval')
            if schedule_type == 'interval':
                # For interval-based schedules, set next send time
                interval_days = schedule.get('interval_days', 7)
                next_send = datetime.now() + timedelta(days=interval_days)
                update_schedule_sent_time(schedule_id, next_send)
                logger.info(f"   ✓ Schedule updated (next send: {next_send})")
            else:
                # For date-based and before_due schedules, just update last_sent_at (no next_send_at)
                update_schedule_sent_time(schedule_id, None)
                logger.info(f"   ✓ Schedule updated (last sent: {datetime.now().date()})")
        
        logger.info("")
        logger.info("=" * 80)
        logger.info(f"✅ NOTIFICATION PROCESS COMPLETE - {'SUCCESS' if success else 'FAILED'}")
        logger.info("=" * 80)
        
        return {
            "success": success,
            "recipient": recipient['email'],
            "subject": subject,
            "schedule_id": schedule_id
        }
    
    def send_direct_notification(
        self,
        recipient_id: int,
        user_id: int,
        notification_type: str,
        context: Optional[Dict] = None,
        template: Optional[str] = None,
        payment_link: Optional[str] = None
    ) -> Dict:
        """Send a direct notification without a schedule."""
        logger.info("")
        logger.info("🚀 STARTING NOTIFICATION SEND (Direct)")
        logger.info(f"   Recipient ID: {recipient_id}")
        logger.info(f"   User ID: {user_id}")
        logger.info(f"   Notification Type: {notification_type}")
        logger.info(f"   Context: {context}")
        logger.info(f"   Has Template: {template is not None}")
        logger.info(f"   Payment Link: {payment_link}")
        
        recipient = get_recipient(recipient_id, user_id=user_id)
        if not recipient:
            logger.error(f"   ❌ Recipient not found (ID: {recipient_id})")
            return {"success": False, "error": "Recipient not found"}
        logger.info(f"   ✓ Recipient found: {recipient.get('name', 'Unnamed')} ({recipient.get('email', 'No email')})")
        
        smtp_config_id = recipient.get('smtp_config_id')
        logger.info(f"   Looking for SMTP config (ID: {smtp_config_id})...")
        smtp_config = get_smtp_config(config_id=smtp_config_id, user_id=user_id) if smtp_config_id else None
        if not smtp_config:
            logger.info("   No SMTP config ID or not found, trying to get default...")
            smtp_config = get_smtp_config(user_id=user_id)
        
        if not smtp_config:
            logger.error("   ❌ SMTP configuration not found")
            return {"success": False, "error": "SMTP configuration not found"}
        logger.info(f"   ✓ SMTP config found: {smtp_config.get('name', 'Unnamed')}")
        
        # Generate email content
        logger.info("")
        logger.info("🤖 Generating email content with AI...")
        try:
            subject, body = self._generate_email_content(
                notification_type=notification_type,
                recipient=recipient,
                context=context,
                template=template,
                payment_link=payment_link,
                sender_name=smtp_config.get('from_name', '')
            )
            logger.info(f"   ✓ Email content generated")
            logger.info(f"   Subject: {subject}")
            logger.info(f"   Body preview: {body[:100]}...")
        except Exception as e:
            logger.error(f"   ❌ Failed to generate email content: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return {"success": False, "error": f"Failed to generate email: {str(e)}"}
        
        # Send email
        logger.info("")
        success = self._send_email(
            smtp_config=smtp_config,
            to_email=recipient['email'],
            subject=subject,
            body=body,
            from_name=smtp_config.get('from_name')
        )
        
        # Log notification
        logger.info("")
        logger.info("📝 Logging notification to database...")
        log_notification({
            'schedule_id': None,
            'recipient_id': recipient_id,
            'notification_type': notification_type,
            'subject': subject,
            'body': body,
            'status': 'sent' if success else 'failed',
            'error_message': None if success else "SMTP send failed"
        }, user_id=user_id)
        logger.info(f"   ✓ Notification logged (status: {'sent' if success else 'failed'})")
        
        logger.info("")
        logger.info("=" * 80)
        logger.info(f"✅ NOTIFICATION PROCESS COMPLETE - {'SUCCESS' if success else 'FAILED'}")
        logger.info("=" * 80)
        
        return {
            "success": success,
            "recipient": recipient['email'],
            "subject": subject
        }
    
    def check_and_send_due_notifications(self, user_id: int) -> List[Dict]:
        """Check schedules and send notifications that are due."""
        from .notifications_db import get_payment, get_worker, get_client, get_vendor
        
        schedules = list_schedules(user_id=user_id, enabled_only=True)
        results = []
        
        now = datetime.now()
        today = now.date()
        
        for schedule in schedules:
            schedule_type = schedule.get('schedule_type', 'interval')
            should_send = False
            
            if schedule_type == 'interval':
                # Interval-based scheduling
                next_send_at = schedule.get('next_send_at')
                if next_send_at:
                    try:
                        next_send = datetime.fromisoformat(next_send_at).date()
                        if today >= next_send:
                            should_send = True
                    except Exception as e:
                        logger.error(f"Error parsing next_send_at for schedule {schedule['id']}: {e}")
                elif not schedule.get('last_sent_at'):
                    # Never sent, send now
                    should_send = True
            
            elif schedule_type == 'date':
                # Date-based scheduling - send only once on the scheduled date
                scheduled_date = schedule.get('scheduled_date')
                if scheduled_date:
                    try:
                        if isinstance(scheduled_date, str):
                            scheduled = datetime.fromisoformat(scheduled_date).date()
                        else:
                            scheduled = scheduled_date
                        # Only send if today is exactly the scheduled date
                        if today == scheduled:
                            # Check if already sent today
                            last_sent = schedule.get('last_sent_at')
                            if last_sent:
                                try:
                                    last_sent_date = datetime.fromisoformat(last_sent).date()
                                    # Only send if not sent today
                                    if last_sent_date != today:
                                        should_send = True
                                except:
                                    should_send = True
                            else:
                                # Never sent, send now
                                should_send = True
                    except Exception as e:
                        logger.error(f"Error parsing scheduled_date for schedule {schedule['id']}: {e}")
            
            elif schedule_type == 'before_due':
                # Before due date scheduling - send only once on the calculated notification date
                payment_id = schedule.get('payment_id')
                days_before = schedule.get('days_before_due', 7)
                
                if payment_id:
                    payment = get_payment(payment_id)
                    if payment:
                        due_date_str = payment.get('due_date')
                        if due_date_str:
                            try:
                                if isinstance(due_date_str, str):
                                    due_date = datetime.fromisoformat(due_date_str).date()
                                else:
                                    due_date = due_date_str
                                
                                # Calculate when notification should be sent
                                notification_date = due_date - timedelta(days=days_before)
                                
                                # Only send if today is exactly the notification date (not before or after)
                                if today == notification_date:
                                    # Check if already sent today
                                    last_sent = schedule.get('last_sent_at')
                                    if last_sent:
                                        try:
                                            last_sent_date = datetime.fromisoformat(last_sent).date()
                                            # Only send if not sent today
                                            if last_sent_date != today:
                                                should_send = True
                                        except:
                                            should_send = True
                                    else:
                                        # Never sent, send now
                                        should_send = True
                            except Exception as e:
                                logger.error(f"Error processing before_due schedule {schedule['id']}: {e}")
            
            if should_send:
                try:
                    result = self.send_notification(schedule['id'], user_id=user_id, force=True)
                    results.append(result)
                except Exception as e:
                    logger.error(f"Error sending notification for schedule {schedule['id']}: {e}")
                    results.append({"success": False, "error": str(e), "schedule_id": schedule['id']})
        
        return results
    
    def create_payment_based_schedules(
        self, 
        payment_id: int,
        user_id: int,
        days_before: List[int] = [7, 3, 1],
        email_template: Optional[str] = None
    ) -> List[int]:
        """Create multiple schedules for a payment (reminders before due date)."""
        from .notifications_db import get_payment, create_schedule, get_worker, get_client, get_vendor
        
        payment = get_payment(payment_id)
        if not payment:
            logger.error(f"Payment {payment_id} not found")
            return []
        
        # Use client_email from payment if available (for receive payments)
        recipient_email = payment.get('client_email')
        recipient_name = payment.get('client_name')
        
        # If client_email is not available, try to get from entity (for backward compatibility)
        if not recipient_email:
            entity_type = payment['entity_type']
            entity_id = payment['entity_id']
            
            if entity_type == 'worker':
                entity = get_worker(entity_id)
                if entity:
                    recipient_email = entity.get('email')
                    recipient_name = entity.get('name')
            elif entity_type == 'client':
                entity = get_client(entity_id)
                if entity:
                    recipient_email = entity.get('email')
                    recipient_name = entity.get('name')
            elif entity_type == 'vendor':
                entity = get_vendor(entity_id)
                if entity:
                    recipient_email = entity.get('email')
                    recipient_name = entity.get('name')
        
        if not recipient_email:
            logger.error(f"Could not find email for payment {payment_id}")
            return []
        
        # Use 'client' as the entity type for receive payments with client_email
        entity_type = 'client' if payment.get('payment_type') == 'receive' and recipient_email else payment.get('entity_type', 'client')
        
        # Create or get recipient
        from .notifications_db import list_recipients, create_recipient
        recipients = list_recipients(user_id=user_id)
        recipient = None
        for r in recipients:
            if r['email'] == recipient_email and r['type'] == entity_type:
                recipient = r
                break
        
        if not recipient:
            recipient_data = {
                'name': recipient_name or f"{entity_type.title()} {entity_id}",
                'email': recipient_email,
                'type': entity_type
            }
            recipient_id = create_recipient(recipient_data, user_id=user_id)
            recipient = {'id': recipient_id, **recipient_data}
        else:
            recipient_id = recipient['id']
        
        # Determine notification type
        if payment['payment_type'] == 'receive':
            notification_type = 'payment_request'
        else:
            notification_type = 'payment_reminder'
        
        # Check if 0 is in the list (send immediately)
        send_immediately = 0 in days_before
        # Filter out 0 from days_before for scheduled reminders
        scheduled_days = [d for d in days_before if d != 0]
        
        # Create schedules for each day before due (excluding 0)
        schedule_ids = []
        for days in scheduled_days:
            schedule_data = {
                'name': f"Payment {payment_id} - {days} days before due",
                'recipient_id': recipient_id,
                'payment_id': payment_id,
                'notification_type': notification_type,
                'schedule_type': 'before_due',
                'days_before_due': days,
                'enabled': True,
                'payment_link': payment.get('payment_link', ''),
                'email_template': email_template or '',
                'trigger_condition': f"Payment due in {days} days"
            }
            schedule_id = create_schedule(schedule_data, user_id=user_id)
            schedule_ids.append(schedule_id)
            logger.info(f"Created schedule {schedule_id} for payment {payment_id} ({days} days before due)")
        
        # If 0 was in the list, send notification immediately
        if send_immediately:
            logger.info(f"🚀 Sending immediate notification for payment {payment_id} (0 days = instant)")
            try:
                # Prepare context for the notification
                context = {
                    'amount': payment.get('amount', 0),
                    'due_date': payment.get('due_date', ''),
                    'invoice_number': payment.get('invoice_number', ''),
                    'project_name': payment.get('project_name', ''),
                    'description': payment.get('description', '')
                }
                
                # Send immediate notification
                result = self.send_direct_notification(
                    recipient_id=recipient_id,
                    user_id=user_id,
                    notification_type=notification_type,
                    context=context,
                    template=email_template,
                    payment_link=payment.get('payment_link', '')
                )
                
                if result.get('success'):
                    logger.info(f"✅ Immediate notification sent successfully to {result.get('recipient', 'unknown')}")
                else:
                    logger.error(f"❌ Failed to send immediate notification: {result.get('error', 'unknown error')}")
            except Exception as e:
                logger.error(f"❌ Error sending immediate notification: {e}")
                import traceback
                logger.error(traceback.format_exc())
        
        return schedule_ids


# Global instance
notification_service = NotificationService()

