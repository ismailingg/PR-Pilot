from pydantic import BaseModel, Field, field_validator
from typing import List, Optional
from enum import Enum


class VerdictStatus(str, Enum):
    STRONGLY_RECOMMEND_MERGE  = "strongly_recommend_merge"
    MERGE_WITH_SUGGESTIONS    = "merge_with_suggestions"
    NEEDS_WORK                = "needs_work"
    DO_NOT_MERGE              = "do_not_merge"
    # Legacy
    MERGE                     = "merge"
    BLOCK                     = "block"
    ADVISE                    = "merge_with_advice"
    APPROVE_WITH_MINOR_CHANGES = "approve_with_minor_changes"
    NEEDS_HUMAN_REVIEW        = "needs_human_review"


class FindingSeverity(str, Enum):
    LOW      = "low"
    MEDIUM   = "medium"
    HIGH     = "high"
    CRITICAL = "critical"


class CodeFinding(BaseModel):
    filename:   str           = Field(..., description="Filename with the issue")
    line_start: Optional[int] = Field(None)
    line_end:   Optional[int] = Field(None)
    severity:   FindingSeverity = Field(..., description="low | medium | high | critical")
    suggestion: Optional[str] = Field(None)

    @field_validator("severity", mode="before")
    @classmethod
    def coerce_severity(cls, v: object) -> str:
        """Never crash — map anything unrecognised to 'low'."""
        if v is None:
            return "low"
        if isinstance(v, str):
            n = v.strip().lower()
            if n in ("low", "medium", "high", "critical"):
                return n
            # common aliases
            alias = {
                "none": "low", "": "low", "n/a": "low",
                "informational": "low", "info": "low",
                "warn": "medium", "warning": "medium",
                "error": "high", "err": "high",
            }
            return alias.get(n, "low")   # unknown → low, never raise
        return v


class IntentSummary(BaseModel):
    goal:               str       = Field(..., description="Goal of the PR")
    acceptance_criteria: List[str] = Field(default_factory=list)
    risks_mentioned:    List[str]  = Field(default_factory=list)


class CodeReviewReport(BaseModel):
    intent_summary:      IntentSummary  = Field(...)
    code_findings:       List[CodeFinding] = Field(default_factory=list)
    overall_assessment:  str            = Field(...)
    specific_suggestions: List[str]     = Field(default_factory=list)
    quality_score:       float          = Field(..., ge=0.0, le=10.0)
    security_score:      float          = Field(..., ge=0.0, le=10.0)


class ReviewVerdict(BaseModel):
    verdict:       VerdictStatus = Field(...)
    confidence:    float         = Field(..., ge=0, le=1)
    summary:       str           = Field(...)
    comment_draft: str           = Field(...)

    @field_validator("verdict", mode="before")
    @classmethod
    def coerce_verdict(cls, v: object) -> str:
        """
        Map any string the agent produces to a valid VerdictStatus.
        Handles: human-readable, title-case, spaced, underscored variants.
        Falls back to 'needs_work' for anything genuinely unrecognised
        so the crew never crashes on a verdict string.
        """
        if v is None:
            return "needs_work"
        if isinstance(v, str):
            n = v.strip().lower()
            mapping = {
                # New format
                "strongly recommended to merge":   "strongly_recommend_merge",
                "strongly recommend merge":         "strongly_recommend_merge",
                "strongly recommend to merge":      "strongly_recommend_merge",
                "strongly_recommended_to_merge":    "strongly_recommend_merge",
                "strongly_recommend_merge":         "strongly_recommend_merge",
                "merge with suggestions":           "merge_with_suggestions",
                "merge_with_suggestions":           "merge_with_suggestions",
                "merge with advice":                "merge_with_suggestions",
                "approve with minor changes":       "merge_with_suggestions",
                "approve_with_minor_changes":       "merge_with_suggestions",
                "needs work":                       "needs_work",
                "needs_work":                       "needs_work",
                "needs human review":               "needs_work",
                "needs_human_review":               "needs_work",
                "do not merge":                     "do_not_merge",
                "do_not_merge":                     "do_not_merge",
                "block":                            "do_not_merge",
                # Legacy passthrough
                "merge":                            "merge",
                "merge_with_advice":                "merge_with_advice",
            }
            if n in mapping:
                return mapping[n]
            # Partial match fallback — catches things like
            # "Strongly Recommended to Merge (clean code)" etc.
            if "strongly" in n and "merge" in n:
                return "strongly_recommend_merge"
            if "do not" in n or "do_not" in n:
                return "do_not_merge"
            if "suggestion" in n or "minor" in n or "advice" in n:
                return "merge_with_suggestions"
            if "merge" in n:
                return "strongly_recommend_merge"
            # Total fallback — unknown string, don't crash, just flag for review
            return "needs_work"
        return v

    @field_validator("confidence", mode="before")
    @classmethod
    def coerce_confidence(cls, v: object) -> float:
        """
        Accept confidence as a percentage string ("94%"), a float (0.94),
        or an integer (94). Never crash.
        """
        if v is None:
            return 0.7
        if isinstance(v, str):
            v = v.strip().rstrip("%")
            try:
                f = float(v)
                return f / 100.0 if f > 1.0 else f
            except ValueError:
                return 0.7
        if isinstance(v, (int, float)):
            f = float(v)
            return f / 100.0 if f > 1.0 else f
        return 0.7