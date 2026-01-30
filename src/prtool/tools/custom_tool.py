from crewai.tools import BaseTool
from  pathlib import Path

class Read_PR_Diff(BaseTool):
    name : str = "Read PR Diff File"
    description : str = (
       "Reads the unified git diff from data/{test_case}/diff.txt. "
        "Use this to see the actual code changes."
    )

    def _run(self, test_case: str) -> str:
        