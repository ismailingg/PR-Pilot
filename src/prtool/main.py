import sys
import os
import json
import datetime from datetime
from prtool.crew import PrToolCrew

def run():
    if len(sys.argv) != 2:
        print("\n❌ Error: Missing test case name.")
        print("Usage: uv run run_crew <test-folder-name>")
        print("Example: uv run run_crew test-pr-001\n")
        sys.exit(1)
    
    test_case_id = sys.argv[1]
    