from pydantic import BaseModel, Field, field_validator
from typing import List, Optional
from enum import Enum

class VerdictStatus(str, Enum):
    MERGE = "merge"
    BLOCK = "block"
    ADVISE = "merge_with_advice"

    # Recommendation-style verdicts (decider agent v2)
    STRONGLY_RECOMMEND_MERGE = "strongly_recommend_merge"
    APPROVE_WITH_MINOR_CHANGES = "approve_with_minor_changes"
    NEEDS_HUMAN_REVIEW = "needs_human_review"
    DO_NOT_MERGE = "do_not_merge"


class FindingSeverity(str, Enum):
    """Allowed severity values for code findings. Agent must use only these."""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class CodeFinding(BaseModel):  # individual code issues
    filename: str = Field(..., description="The filename of the code that has the issue")
    line_start: Optional[int] = Field(None, description="The starting line number of the issue")
    line_end: Optional[int] = Field(None, description="The ending line number of the issue")
    severity: FindingSeverity = Field(
        ...,
        description="Severity of the issue. Use exactly one of: low, medium, high, critical.",
    )
    suggestion: Optional[str] = Field(None, description="A suggestion for fixing the issue")

    @field_validator("severity", mode="before")
    @classmethod
    def coerce_severity(cls, v: object) -> str:
        """Map 'Informational', 'N/A', or other non-standard values to 'low'."""
        if isinstance(v, str):
            normalized = v.strip().lower()
            if normalized in ("informational", "info", "n/a", "none", "unknown"):
                return "low"
        return v

class IntentSummary(BaseModel): #What the pr is trying to do
    goal: str = Field(...,description="The goal of the PR")
    acceptance_criteria: List[str] = Field(default_factory=list,description="The acceptance criteria for the PR")
    risks_mentioned: List[str] = Field(default_factory=list,description="The risks mentioned in the PR")

class CodeReviewReport(BaseModel): #Report on the code review
    intent_summary: IntentSummary = Field(...,description="The summary of the intent of the PR")
    code_findings: List[CodeFinding] = Field(default_factory=list,description="The findings of the code review")
    overall_assessment: str = Field(...,description="The overall assessment for the PR")
    specific_suggestions: List[str] = Field(default_factory=list,description="Specific suggestions for the PR")
    quality_score: float = Field(..., ge=0.0, le=10.0, description="Overall code quality (0-10)")
    security_score: float = Field(..., ge=0.0, le=10.0, description="Security health (0-10)")

class ReviewVerdict(BaseModel):
    verdict: VerdictStatus = Field(
        ...,
        description="Final recommendation verdict (legacy or recommendation-style).",
    )
    confidence: float = Field(..., ge=0, le=1)
    summary: str = Field(..., description="A summary of why this verdict was chosen")
    comment_draft: str = Field(
        ...,
        description="The GitHub comment as a single line; use escaped newline \\n for line breaks so JSON stays valid.",
    )
    
class ProjectContext(BaseModel):
    tech_stack: str = Field(..., description="The primary languages and frameworks detected (e.g. 'Node.js/React', 'Python/Django')")
    complexity_level: str = Field(..., pattern="^(low|medium|high)$", description="Estimated complexity of the changes")
    files_affected: int = Field(..., description="Approximate number of files changed")
