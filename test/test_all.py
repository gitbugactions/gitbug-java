import subprocess
import tempfile
import uuid
import os
import json
import tqdm
import shutil


def run_command(command):
    return subprocess.run(
        command, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE
    )


def test_help():
    assert run_command("gitbug-java --help").returncode == 0
    assert run_command("gitbug-java -h").returncode == 0


def run_bug(bid, fixed):
    # Setup temporary directory
    temp_dir = os.path.join(tempfile.gettempdir(), bid, str(uuid.uuid4()))
    output_dir = os.path.join(temp_dir, "gitbug-java-output", str(uuid.uuid4()))

    try:
        # Checkout the bug and check correctness
        run = run_command(
            f"gitbug-java checkout {bid} {temp_dir} {'--fixed' if fixed else ''}"
        )
        if run.returncode != 0:
            print(f"{bid} ({fixed}) failed to checkout")
            return

        # Run the bug and check results
        run = run_command(f"gitbug-java run {temp_dir} --output={output_dir}")

        with open(os.path.join(output_dir, bid), "r") as f:
            report = json.loads(f.read())

        if fixed and run.returncode != 0:
            print(f"{bid} failed to reproduce fixed version")
            return False
        elif not fixed and (
            report["failed_tests"] == 0
            or report["expected_tests"] != report["executed_tests"]
        ):
            print(f"{bid} failed to reproduce buggy version")
            return False
        return True
    finally:
        # Cleanup
        shutil.rmtree(temp_dir, ignore_errors=True)
        shutil.rmtree(output_dir, ignore_errors=True)


def test_run_all():
    # Get list of all bugs
    bugs = run_command("gitbug-java bids").stdout.decode("utf-8").strip().split("\n")

    assert len(bugs) == 200

    mixed_bugs = [
        "spring-projects-spring-retry-e6091f790c64",
        "spring-projects-spring-retry-c89b9516d976",
    ]

    results = []
    # Run all bugs
    for bug in tqdm.tqdm(mixed_bugs):
        if bug:
            results.append(run_bug(bug, fixed=False))
            results.append(run_bug(bug, fixed=True))

    assert all(results)
