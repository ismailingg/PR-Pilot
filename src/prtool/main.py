import os
# Suppress LiteLLM's noisy proxy/logging errors
os.environ.setdefault("LITELLM_LOG", "ERROR")
# Also try disabling the standard logging payload that triggers proxy imports
os.environ.setdefault("LITELLM_TURN_OFF_MESSAGE_LOGGING", "true")

import sys
import os
import json
from datetime import datetime
from prtool.crew import PrToolCrew
from pathlib import Path

def run():
    if len(sys.argv) != 2:
        print("\n❌ Error: Missing test case name.")
        print("Usage: uv run run_crew <test-folder-name>")
        print("Example: uv run run_crew test-pr-001\n")
        sys.exit(1)
    
    test_case_id = sys.argv[1]
    data_path = Path(f"data/{test_case_id}")
    if not data_path.exists():
        print(f"❌ Error: Test case folder '{data_path}' not found.")
        sys.exit(1)
    
    inputs = {
        "test_case": test_case_id,
        "data_path": str(data_path),
        "repo_name": "MergeMate-Lab",
        "issue_number": "001",
        "tech_stack": "Detected Technology"
    }
    print(f"\n{'='*60}")
    print(f"🚀 STARTING PHASE 1: THE BRAIN TEST")
    print(f"📂 Folder: data/{test_case_id}")
    print(f"⏰ Time: {datetime.now().strftime('%H:%M:%S')}")
    
    try:
       
        result = PrToolCrew().crew().kickoff(inputs=inputs)

        
        print("\n" + "✅" + " ANALYSIS COMPLETE " + "✅")
        
        print("\n[1] MACHINE-READABLE VERDICT (JSON)")
        print("-" * 40)
       
        print(json.dumps(result.to_dict(), indent=2))

       
        print("\n[2] PROPOSED GITHUB COMMENT")
        print("-" * 40)
        print(result.raw) 
        print("-" * 40)

    except Exception as e:
        print(f"\n💥 CRITICAL ERROR during review: {e}")
        sys.exit(1)
        
if __name__ == "__main__":
    run()