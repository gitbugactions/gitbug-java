#!/usr/bin/env python3

import json
import csv
from pathlib import Path

def build_problem_statement(sample):
    """Build a problem statement from a sample's failing tests."""
    try:
        i = 0 if sample.get("strategy") == "FAIL_PASS" else 1
        actions_runs = sample.get("actions_runs")
        if not actions_runs or not actions_runs[i]:
            raise ValueError("No test results found in the sample data")
            
        failing_tests = [
            test
            for test in actions_runs[i][0]["tests"]
            if test["results"][0]["result"] == "Failure"
        ]
        
        if not failing_tests:
            raise ValueError("No failing tests found in the sample data")
        
        # Build a focused, test-driven problem statement
        problem_statement = ""
        
        if project_name := sample.get('project_name'):
            problem_statement += f"Project: {project_name}\n\n"
        
        problem_statement += (
            "The test suite has uncovered a bug in the code. Below are the failing tests "
            "that pinpoint the incorrect behavior. Each test failure provides clues about "
            "what's wrong and how the code should behave.\n\n"
            "Current test failures:\n"
        )
        
        # Add each failing test with its details
        for test in failing_tests:
            test_name = test.get('name', 'Unknown test')
            test_class = test.get('classname', 'Unknown class')
            test_result = test.get('results', [{}])[0]
            error_type = test_result.get('type', 'Unknown error')
            error_msg = test_result.get('message', 'No error message provided')
            
            problem_statement += f"\nTest: {test_class}#{test_name}\n"
            problem_statement += f"Type: {error_type}\n"
            problem_statement += f"Message: {error_msg}\n"
            
     
        # Add instructions focused on using tests for verification
        problem_statement += (
            "\nFix the bug in the code to make the failing tests pass. The tests act as both a bug report "
            "and a verification tool."
        )
        
        return problem_statement

    except Exception as e:
        raise ValueError(f"Error building problem statement: {str(e)}")

# Path to the bugs directory
bugs_dir = Path(__file__).parent.parent / "data" / "bugs"

# Output CSV file
output_file = Path(__file__).parent.parent / "dataset.csv"

# Create a list to store all entries
entries = []

# Read ignored list
ignored_bugs = set()
ignored_path = Path(__file__).parent / "ignored.txt"
with open(ignored_path, "r") as f:
    for line in f.readlines():
        ignored_bugs.add(line.strip())

# Process each json file in the bugs directory
for json_file in bugs_dir.glob("*.json"):
    pid = json_file.stem

    with json_file.open() as f:
        for line in f:
            bug_info = json.loads(line)
            bid = bug_info["commit_hash"][:12]

            if f"{pid}-{bid}" in ignored_bugs:
                print(f"Ignoring {pid}-{bid}")
                continue

            # Create instance_id
            instance_id = f"{pid}-{bid}".lower()

            # Create image tag
            image_tag = f"gitbugjava.eval.x86_64.{instance_id}:msbench-0.1.0"

            # Add entry
            entries.append(
                {
                    "instance_id": instance_id,
                    "problem_statement": build_problem_statement(bug_info),
                    "image_tag": image_tag,
                    "bug_patch": bug_info["bug_patch"],
                }
            )

# Write to CSV
with output_file.open("w", newline="") as f:
    writer = csv.DictWriter(
        f, fieldnames=["instance_id", "problem_statement", "image_tag", "bug_patch"]
    )
    writer.writeheader()
    writer.writerows(entries)

print(f"Created dataset with {len(entries)} entries at {output_file}")
