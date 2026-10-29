#!/usr/bin/env python3
"""Master Validation Runner for Workshop OS.
Discovers and executes all versioned validation scripts.
"""
import subprocess
import glob
import sys
from pathlib import Path

def main():
    repo = Path(__file__).resolve().parents[1]
    scripts = sorted(glob.glob("scripts/validate_os12_*.py"))
    
    print(f"Found {len(scripts)} validation scripts. Starting run...\n")
    
    passed = 0
    failed = 0
    results = []

    for script in scripts:
        print(f"Running {script}...", end=" ", flush=True)
        try:
            # Run each script as a separate process to isolate crashes
            process = subprocess.run(
                ["python3", script, "--repo", str(repo)],
                capture_output=True,
                text=True
            )
            if process.returncode == 0:
                print("✅ PASS")
                passed += 1
            else:
                print("❌ FAIL")
                failed += 1
                results.append((script, process.stdout + process.stderr))
        except Exception as e:
            print(f"⚠️ ERROR: {e}")
            failed += 1
            results.append((script, str(e)))

    print(f"\n{'='*40}")
    print(f"Validation Summary: {passed} Passed, {failed} Failed")
    print(f"{'='*40}")

    if failed > 0:
        print("\nFailure Details:")
        for script, output in results:
            print(f"\n--- {script} ---")
            print(output)
        sys.exit(1)
    
    sys.exit(0)

if __name__ == "__main__":
    main()
