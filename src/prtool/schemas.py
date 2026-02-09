from pydantic import BaseModel,Field
from typing import List, Optional
from enum import Enum

class VerdictStatus(str, Enum):
    MERGE = "merge"
    BLOCK = "block"
    ADVISE = "merge_with_advice"

class CodeFinding(BaseModel): #indiviual code issues
    filename: str= Field(...,description="The filename of the code that has the issue")
    line_start: Optional[int] = Field(None,description="The starting line number of the issue")
    line_end: Optional[int]= Field(None,description="The ending line number of the issue")
    severity: str = Field(..., pattern="^(low|medium|high|critical|Low|Medium|High|Critical)$", description="The severity of the issue")   
    suggestion: Optional[str] = Field(None,description="A suggestion for fixing the issue")

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
    verdict: VerdictStatus = Field(..., description="The final decision: merge, block, or merge_with_advice")
    confidence: float = Field(..., ge=0, le=1)
    summary: str = Field(..., description="A summary of why this verdict was chosen")
    comment_draft: str = Field(..., description="The GitHub comment. Use literal '\\n' for newlines.")
    
class ProjectContext(BaseModel):
    tech_stack: str = Field(..., description="The primary languages and frameworks detected (e.g. 'Node.js/React', 'Python/Django')")
    complexity_level: str = Field(..., pattern="^(low|medium|high)$", description="Estimated complexity of the changes")
    files_affected: int = Field(..., description="Approximate number of files changed")
