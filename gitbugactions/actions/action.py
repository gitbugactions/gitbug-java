import logging
import re
import shutil
import os, subprocess, threading
import traceback


class Action:
    # Class to represent a GitHub Action
    # Note: We consider only the major version of the action, thus we ignore the minor and patch versions
    CLONE_SEM = threading.Semaphore(16)

    def __init__(self, declaration: str):
        self.declaration = declaration
        match = re.match(r"^([^/@]+)/([^/@]+)(/([^@]*))?(@(.*))?$", self.declaration)
        assert match != None and len(match.groups()) == 6 and match.group(6) is not None
        self.org = match.group(1)
        self.repo = match.group(2)
        self.path = match.group(4)
        self.ref = match.group(6)

    def download(self, action_dir: str):
        """
        Download the action to the action dir
        """
        from gitbugactions.util import clone_repo

        logging.info(f"Downloading action {self.declaration} to {action_dir}")

        # If the action is already in the cache, raise an exception
        if os.path.exists(action_dir):
            logging.warning(f"Action directory already exists: {action_dir}")
            return

        try:
            with Action.CLONE_SEM:
                # Clone the action to the action dir using pygit2
                clone_repo(f"https://github.com/{self.org}/{self.repo}.git", action_dir)

                # Checkout the action version
                run = subprocess.run(
                    f"git checkout {self.ref}",
                    cwd=action_dir,
                    shell=True,
                    capture_output=True,
                )
                assert run.returncode == 0

                # Remove gitignore so that act doesn't have to
                gitignore_path = os.path.join(action_dir, ".gitignore")
                if os.path.exists(gitignore_path):
                    os.remove(gitignore_path)
        except Exception:
            # If something goes wrong, delete the action dir
            shutil.rmtree(action_dir, ignore_errors=True)
            print(traceback.format_exc())
            raise Exception(
                f"Error while downloading action {self.declaration}: {traceback.format_exc()}"
            )

    def __hash__(self) -> int:
        return hash((self.org, self.repo, self.ref))

    def __eq__(self, other):
        return (
            self.org == other.org and self.repo == self.repo and self.ref == other.ref
        )
