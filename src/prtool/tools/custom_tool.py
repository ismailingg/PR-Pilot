from crewai.tools import BaseTool
from  pathlib import Path

class Read_PR_Diff(BaseTool):
    name : str = "Read PR Diff File"
    description : str = (
       "Reads the unified git diff from data/{test_case}/diff.txt. "
        "Use this to see the actual code changes."
    )

    def _run(self, test_case: str) -> str:
        path = Path(f"data/{test_case}/diff.txt")
        if path.exists():
            return path.read_text(encoding="utf-8")
        else:
            return f"ERROR: diff.txt not found in {test_case}"

class ReadLocalPRBody(BaseTool):
    name: str = "Read Local PR Body"
    description: str = (
        "Reads the PR description from data/{test_case}/pr_body.md. "
        "Use this to understand the developer's intent."
    )
    def _run(self, test_case: str) -> str:
        path = Path(f"data/{test_case}/pr_body.md")
        return path.read_text(encoding="utf-8") if path.exists() else f"ERROR: pr_body.md not found in {test_case}"

class ReadLocalIssue(BaseTool):
    name: str = "Read Local Issue File"
    description: str = (
        "Reads the original GitHub issue from data/{test_case}/issue.md. "
        "Use this to verify if the code actually solves the requirement."
    )
    def _run(self, test_case: str) -> str:
        path = Path(f"data/{test_case}/issue.md")
        return path.read_text(encoding="utf-8") if path.exists() else f"ERROR: issue.md not found in {test_case}"

class FormatReviewComment(BaseTool):
    name: str = "Format Review Comment"
    description: str = "Formats structured JSON data into a beautiful Markdown comment for the CLI output."

    def _run(self, verdict: str, quality: float, summary: str) -> str:
        # This is a pure string helper, no LLM required.
        return f"""
### 🤖 MergeMate Phase 1 Review
**Verdict:** {verdict.upper()} | **Quality:** {quality}/10

**Summary:** {summary} """