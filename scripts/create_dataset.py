#!/usr/bin/env python3

import json
import csv
from pathlib import Path

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
            image_tag = f"gitbugjava.eval.x86_64.{instance_id}:msbench-0.0.0"

            # Add entry
            entries.append(
                {
                    "instance_id": instance_id,
                    "problem_statement": "repair",
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
