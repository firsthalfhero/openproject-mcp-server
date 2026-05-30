"""Data models for OpenProject MCP Server."""
from typing import Optional, List
from datetime import datetime
from pydantic import BaseModel, Field, validator


class Project(BaseModel):
    """Project data model."""
    id: Optional[int] = None
    name: str = Field(..., min_length=1, max_length=255, description="Project name")
    description: Optional[str] = Field(default="", description="Project description")
    status: Optional[str] = Field(default="active", description="Project status")
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


class WorkPackage(BaseModel):
    """Work package data model."""
    id: Optional[int] = None
    subject: str = Field(..., min_length=1, max_length=255, description="Work package subject")
    description: Optional[str] = Field(default="", description="Work package description")
    project_id: int = Field(..., gt=0, description="Project ID this work package belongs to")
    type_id: Optional[int] = Field(default=1, description="Work package type ID (default: 1 = Task)")
    status_id: Optional[int] = Field(default=1, description="Work package status ID (default: 1 = New)")
    priority_id: Optional[int] = Field(default=2, description="Work package priority ID (default: 2 = Normal)")
    assignee_id: Optional[int] = Field(default=None, description="Assigned user ID")
    parent_id: Optional[int] = Field(default=None, description="Parent work package ID for hierarchy")
    start_date: Optional[str] = Field(default=None, description="Start date in YYYY-MM-DD format")
    due_date: Optional[str] = Field(default=None, description="Due date in YYYY-MM-DD format")
    estimated_hours: Optional[float] = Field(default=None, description="Estimated hours")
    done_ratio: Optional[int] = Field(default=0, ge=0, le=100, description="Completion percentage (0-100)")
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


class WorkPackageRelation(BaseModel):
    """Work package relation data model for dependencies."""
    id: Optional[int] = None
    from_work_package_id: int = Field(..., gt=0, description="Source work package ID")
    to_work_package_id: int = Field(..., gt=0, description="Target work package ID")
    relation_type: str = Field(default="follows", description="Relation type (follows, precedes, blocks, blocked, relates, duplicates, duplicated)")
    reverse_type: Optional[str] = Field(default=None, description="Automatically generated reverse relation type")
    description: Optional[str] = Field(default="", description="Description of the relation")
    lag: Optional[int] = Field(default=0, description="Working days between finish of predecessor and start of successor")
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


class ProjectCreateRequest(BaseModel):
    """Request model for creating a project."""
    name: str = Field(..., min_length=1, max_length=255)
    description: Optional[str] = ""
    status: Optional[str] = "active"


class WorkPackageCreateRequest(BaseModel):
    """Request model for creating a work package."""
    subject: str = Field(..., min_length=1, max_length=255)
    description: Optional[str] = ""
    project_id: int = Field(..., gt=0)
    type_id: Optional[int] = 1
    status_id: Optional[int] = 1
    priority_id: Optional[int] = 2
    assignee_id: Optional[int] = None
    parent_id: Optional[int] = None
    start_date: Optional[str] = None
    due_date: Optional[str] = None
    estimated_hours: Optional[float] = None

    @validator('start_date', 'due_date')
    def validate_date_format(cls, v):
        """Validate date format is YYYY-MM-DD."""
        if v is not None:
            try:
                datetime.strptime(v, "%Y-%m-%d")
            except ValueError:
                raise ValueError("Date must be in YYYY-MM-DD format")
        return v
    
    @validator('due_date')
    def validate_due_after_start(cls, v, values):
        """Validate due date is after start date."""
        if v and values.get('start_date'):
            try:
                start = datetime.strptime(values['start_date'], "%Y-%m-%d")
                due = datetime.strptime(v, "%Y-%m-%d")
                if due < start:
                    raise ValueError("Due date must be after start date")
            except ValueError as e:
                if "Date must be in YYYY-MM-DD format" not in str(e):
                    raise ValueError("Due date must be after start date")
        return v

    @validator('estimated_hours')
    def validate_estimated_hours(cls, v):
        """Validate estimated hours is positive."""
        if v is not None and v <= 0:
            raise ValueError("Estimated hours must be positive")
        return v

    @validator('parent_id')
    def validate_parent_id(cls, v, values):
        """Validate parent ID is not the same as work package ID (can't validate at creation time)."""
        if v is not None and v <= 0:
            raise ValueError("Parent ID must be a positive integer")
        return v


class WorkPackageRelationCreateRequest(BaseModel):
    """Request model for creating work package relations."""
    from_work_package_id: int = Field(..., gt=0, description="Source work package ID")
    to_work_package_id: int = Field(..., gt=0, description="Target work package ID")
    relation_type: str = Field(default="follows", description="Relation type (follows, precedes, blocks, blocked, relates, duplicates, duplicated)")
    description: Optional[str] = Field(default="", description="Description of the relation")
    lag: Optional[int] = Field(default=0, description="Working days between finish of predecessor and start of successor")

    @validator('to_work_package_id')
    def validate_different_work_packages(cls, v, values):
        """Validate that from and to work packages are different."""
        if v and values.get('from_work_package_id') and v == values['from_work_package_id']:
            raise ValueError("Work package cannot have a relation with itself")
        return v

    @validator('relation_type')
    def validate_relation_type(cls, v):
        """Validate relation type is supported."""
        valid_relations = ["follows", "precedes", "blocks", "blocked", "relates", "duplicates", "duplicated"]
        if v not in valid_relations:
            raise ValueError(f"Invalid relation type. Must be one of: {', '.join(valid_relations)}")
        return v

    @validator('lag')
    def validate_lag(cls, v):
        """Validate lag is non-negative."""
        if v is not None and v < 0:
            raise ValueError("Lag must be zero or positive (working days)")
        return v


class CommentCreateRequest(BaseModel):
    """Request model for creating a work package comment."""
    comment: str = Field(..., min_length=1, description="Comment text in markdown format")
    internal: bool = Field(default=False, description="Whether the comment is only visible internally")


class ReactionToggleRequest(BaseModel):
    """Request model for toggling an emoji reaction on an activity."""
    reaction: str = Field(..., description="Reaction emoji identifier (e.g., thumbs_up, heart)")


