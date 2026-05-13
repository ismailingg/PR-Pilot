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


class CodeFinding(BaseModel):
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
        """Map 'Informational' / 'info' from the agent to 'low' (mildest level)."""
        if isinstance(v, str):
            normalized = v.strip().lower()
            if normalized in ("informational", "info"):
                return "low"
        return v


class IntentSummary(BaseModel):
    goal: str = Field(..., description="The goal of the PR")
    acceptance_criteria: List[str] = Field(default_factory=list, description="The acceptance criteria for the PR")
    risks_mentioned: List[str] = Field(default_factory=list, description="The risks mentioned in the PR")


class TestCounts(BaseModel):
    total: int = Field(default=0, description="Total number of tests run")
    passed: int = Field(default=0, description="Number of tests that passed")
    failed: int = Field(default=0, description="Number of tests that failed")


class TestExecutionResult(BaseModel):
    status: str = Field(
        ...,
        description="One of: completed, skipped, error, timeout",
    )
    language: Optional[str] = Field(None, description="Detected language: python, nodejs, go, rust, java_maven, ruby")
    passed: bool = Field(default=False, description="True if all tests passed (exit code 0)")
    test_counts: Optional[TestCounts] = Field(None, description="Parsed pass/fail counts if available")
    duration_seconds: Optional[float] = Field(None, description="How long the test run took")
    logs_summary: str = Field(default="", description="Summarised test output — key failures and final result line")
    skip_reason: Optional[str] = Field(None, description="Why tests were skipped, if applicable")


class CodeReviewReport(BaseModel):
    intent_summary: IntentSummary = Field(..., description="The summary of the intent of the PR")
    code_findings: List[CodeFinding] = Field(default_factory=list, description="The findings of the code review")
    overall_assessment: str = Field(..., description="The overall assessment for the PR")
    specific_suggestions: List[str] = Field(default_factory=list, description="Specific suggestions for the PR")
    quality_score: float = Field(..., ge=0.0, le=10.0, description="Overall code quality (0-10)")
    security_score: float = Field(..., ge=0.0, le=10.0, description="Security health (0-10)")
    test_result: Optional[TestExecutionResult] = Field(None, description="Test execution results from the sandbox runner")


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