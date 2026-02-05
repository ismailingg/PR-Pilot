from pydantic import BaseModel
from typing import List, Optional

class CodeFinding(BaseModel): #indiviual code issues
    filename: str= Field(...,description="The filename of the code that has the issue")
    line_start: Optional[int] = Field(None,description="The starting line number of the issue")
    line_end: Optional[int]: Field(None,description="The ending line number of the issue")
    severity: str = Field(...,pattern="^(low|medium|high|critical)$", Description="The severity of the issue")
    description: str = Field(...,Description="A detailed description of the issue")
    suggestion: Optional[str] = Field(None,Description="A suggestion for fixing the issue")

class IntentSummary(BaseModel): #What the pr is trying to do
    goaL: str = Field(...,Description="The goal of the PR")
    acceptance_criteria: List[str] = Field(default_factory=list,Description="The acceptance criteria for the PR")
    risks_mentioned: [List[str]] = Field(default_factory=list,Description="The risks mentioned in the PR")

class CodeReviewReport(BaseModel): #Report on the code review
    intent_summary: IntentSummary = Field(...,Description="The summary of the intent of the PR")
    code_findings: List[CodeFinding] = Field(default_factory=list,Description="The findings of the code review")
    overall_assessment: str = Field(...,Description="The overall assessment for the PR")
    specific_suggestions: List[str] = Field(default_factory=list,Description="Specific suggestions for the PR")
    uality_score: float = Field(..., ge=0.0, le=10.0, description="Overall code quality (0-10)")
    security_score: float = Field(..., ge=0.0, le=10.0, description="Security health (0-10)")

class ReviewVerdict(BaseModel):
    solves_issue: str = Field(..., pattern="^(yes|partial|no)$")
    confidence: float = Field(..., ge=0.0, le=1.0)
    summary: str = Field(..., description="One-sentence executive summary")
    comment_draft: str = Field(..., description="The full markdown text for the GitHub comment")
    
class ProjectContext(BaseModel):
    tech_stack: str = Field(..., description="The primary languages and frameworks detected (e.g. 'Node.js/React', 'Python/Django')")
    complexity_level: str = Field(..., pattern="^(low|medium|high)$", description="Estimated complexity of the changes")
    files_affected: int = Field(..., description="Approximate number of files changed")
    