"""Validation utilities for OpenProject MCP Server."""
from typing import Any
import re
import unicodedata
from datetime import datetime
import structlog

logger = structlog.get_logger()


# Allowed OpenProject project status codes (used for _links.status.href).
VALID_PROJECT_STATUSES = {
    "on_track",
    "off_track",
    "at_risk",
    "not_started",
    "finished",
    "discontinued",
}

# German umlaut / eszett transliterations applied before slugifying.
_TRANSLITERATIONS = {
    "ä": "ae", "ö": "oe", "ü": "ue", "ß": "ss",
    "Ä": "ae", "Ö": "oe", "Ü": "ue",
}


def validate_project_status(status: str) -> None:
    """Validate a project status code against the allowed OpenProject set.

    Args:
        status: Project status code (e.g. "finished")

    Raises:
        ValueError: If the status is not one of VALID_PROJECT_STATUSES
    """
    if status not in VALID_PROJECT_STATUSES:
        allowed = ", ".join(sorted(VALID_PROJECT_STATUSES))
        raise ValueError(f"Invalid status '{status}'. Must be one of: {allowed}")


def generate_identifier(name: str) -> str:
    """Derive a URL-safe OpenProject project identifier from a name.

    Rules: German umlaut transliteration (ä->ae, ö->oe, ü->ue, ß->ss), then
    NFKD-strip remaining accents, lowercase, keep [a-z0-9_], replace every
    other character (incl. '&' and whitespace) with '-', collapse repeated
    '-', and trim leading/trailing '-'. Falls back to "project" if empty.

    Examples:
        "B&R" -> "b-r", "FH " -> "fh",
        "Jenoptik_WeMatch" -> "jenoptik_wematch", "COLOP KG" -> "colop-kg"
    """
    text = name or ""

    # Explicit German transliteration before unicode normalization.
    for src, dst in _TRANSLITERATIONS.items():
        text = text.replace(src, dst)

    # Strip remaining accents (é -> e, etc.).
    text = unicodedata.normalize("NFKD", text)
    text = "".join(ch for ch in text if not unicodedata.combining(ch))

    text = text.lower()

    # Replace any disallowed character with '-'. Allowed: a-z, 0-9, '_'.
    text = re.sub(r"[^a-z0-9_]+", "-", text)

    # Collapse repeated '-' and trim from the ends.
    text = re.sub(r"-{2,}", "-", text).strip("-")

    return text or "project"


def validate_work_package_data(project_id: int, subject: str) -> None:
    """Validate basic work package creation data.
    
    Args:
        project_id: Project ID for the work package
        subject: Work package subject/title
        
    Raises:
        ValueError: If validation fails
    """
    if not isinstance(project_id, int) or project_id <= 0:
        raise ValueError("project_id must be a positive integer")
    
    if not subject or not subject.strip():
        raise ValueError("subject cannot be empty")
    
    if len(subject) > 255:
        raise ValueError("subject cannot exceed 255 characters")


def validate_project_data(name: str, description: str = "") -> None:
    """Validate project creation data.
    
    Args:
        name: Project name
        description: Project description
        
    Raises:
        ValueError: If validation fails
    """
    if not name or not name.strip():
        raise ValueError("project name cannot be empty")
    
    if len(name) > 255:
        raise ValueError("project name cannot exceed 255 characters")
    
    if description and len(description) > 65535:
        raise ValueError("project description cannot exceed 65535 characters")


def validate_id(value: Any, field_name: str) -> None:
    """Validate that a value is a positive integer ID.
    
    Args:
        value: Value to validate
        field_name: Name of the field for error messages
        
    Raises:
        ValueError: If validation fails
    """
    if not isinstance(value, int) or value <= 0:
        raise ValueError(f"{field_name} must be a positive integer")


def validate_date_format(date_string: str, field_name: str = "date") -> None:
    """Validate date string format.
    
    Args:
        date_string: Date string to validate
        field_name: Name of the field for error messages
        
    Raises:
        ValueError: If date format is invalid
    """
    if not date_string:
        return  # Optional dates can be empty
    
    try:
        datetime.strptime(date_string, "%Y-%m-%d")
    except ValueError:
        raise ValueError(f"{field_name} must be in YYYY-MM-DD format")


def validate_relation_type(relation_type: str) -> None:
    """Validate work package relation type.
    
    Args:
        relation_type: Relation type to validate
        
    Raises:
        ValueError: If relation type is invalid
    """
    valid_relations = ["follows", "precedes", "blocks", "blocked", "relates"]
    if relation_type not in valid_relations:
        raise ValueError(f"Invalid relation type. Must be one of: {', '.join(valid_relations)}")


def validate_estimated_hours(hours: float) -> None:
    """Validate estimated hours value.
    
    Args:
        hours: Hours to validate
        
    Raises:
        ValueError: If hours value is invalid
    """
    if hours < 0:
        raise ValueError("estimated hours cannot be negative")
    
    if hours > 9999:
        raise ValueError("estimated hours cannot exceed 9999")


def sanitize_input(value: str, max_length: int = None) -> str:
    """Sanitize user input string.
    
    Args:
        value: Input string to sanitize
        max_length: Maximum allowed length
        
    Returns:
        Sanitized string
        
    Raises:
        ValueError: If input exceeds max length
    """
    if not isinstance(value, str):
        value = str(value)
    
    # Strip whitespace and normalize
    sanitized = value.strip()
    
    # Remove control characters except newlines and tabs
    sanitized = re.sub(r'[\x00-\x08\x0B\x0C\x0E-\x1F\x7F]', '', sanitized)
    
    # Check length if specified
    if max_length and len(sanitized) > max_length:
        raise ValueError(f"Input exceeds maximum length of {max_length} characters")
    
    return sanitized


def validate_email(email: str) -> None:
    """Validate email address format.
    
    Args:
        email: Email address to validate
        
    Raises:
        ValueError: If email format is invalid
    """
    if not email:
        raise ValueError("email cannot be empty")
    
    # Basic email validation regex
    email_pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    if not re.match(email_pattern, email):
        raise ValueError("invalid email address format")


def validate_user_data(name: str, email: str = None) -> None:
    """Validate user data.
    
    Args:
        name: User name
        email: User email (optional)
        
    Raises:
        ValueError: If validation fails
    """
    if not name or not name.strip():
        raise ValueError("user name cannot be empty")
    
    if len(name) > 255:
        raise ValueError("user name cannot exceed 255 characters")
    
    if email:
        validate_email(email)


def validate_search_params(query: str = None, limit: int = None, offset: int = None) -> None:
    """Validate search parameters.
    
    Args:
        query: Search query string
        limit: Result limit
        offset: Result offset
        
    Raises:
        ValueError: If validation fails
    """
    if query and len(query) < 2:
        raise ValueError("search query must be at least 2 characters")
    
    if query and len(query) > 500:
        raise ValueError("search query cannot exceed 500 characters")
    
    if limit is not None:
        if not isinstance(limit, int) or limit <= 0:
            raise ValueError("limit must be a positive integer")
        
        if limit > 1000:
            raise ValueError("limit cannot exceed 1000")
    
    if offset is not None:
        if not isinstance(offset, int) or offset < 0:
            raise ValueError("offset must be a non-negative integer")
