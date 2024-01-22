import subprocess
import tempfile
import uuid
import os
import shutil

def run_command(command):
    return subprocess.run(command, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)

def test_help():
    assert run_command("gitbug-java --help").returncode == 0
    assert run_command("gitbug-java -h").returncode == 0

def run_bug(bid, fixed):
    # Setup temporary directory
    temp_dir = os.path.join(tempfile.gettempdir(), bid, str(uuid.uuid4()))   

    try:
        # Checkout the bug and check correctness
        run = run_command(f"gitbug-java checkout {bid} {temp_dir} {'--fixed' if fixed else ''}")
        if run.returncode != 0:
            print(f"{bid} ({fixed}) failed to checkout")
            return

        # Run the bug and check results
        run = run_command(f"gitbug-java run {temp_dir}")
        stdout = run.stdout.decode("utf-8")
        result = stdout.strip().split("\n")[-1]
        if fixed:
            if result != "True":
                print(f"{bid} failed to reproduce fixed version")
        else:
            if result != "False":
                print(f"{bid} failed to reproduce buggy version")
    finally:
        # Cleanup
        shutil.rmtree(temp_dir, ignore_errors=True)

def test_run_all():
    # Get list of all bugs
    bugs = run_command("gitbug-java bids").stdout.decode("utf-8").strip().split("\n")

    assert len(bugs) == 200

    mixed_bugs = [
        "spring-projects-spring-retry-e6091f790c64",
        "spring-projects-spring-retry-c89b9516d976",
    ]

    # Run all bugs
    for bug in mixed_bugs:
        if bug:
            run_bug(bug, fixed=False)
            run_bug(bug, fixed=True)
