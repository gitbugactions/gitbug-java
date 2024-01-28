import re
import os
import sys
import uuid
import json
import docker
import pygit2
import shutil
import logging
import subprocess

from pathlib import Path
from typing import Optional

from gitbugactions.test_executor import TestExecutor
from gitbugactions.docker.export import create_diff_image
from gitbugactions.actions.workflow import GitHubWorkflowFactory
from gitbugactions.actions.actions import ActCacheDirManager, GitHubActions


class Bug(object):
    def __init__(self, bug: dict) -> None:
        for key, value in bug.items():
            setattr(self, key, value)

        self.bug_info = bug
        # replace the clone_url org with the gitbugactions fork
        self.clone_url = re.sub(
            r"https://github.com/.*/",
            "https://github.com/gitbugactions/",
            self.clone_url,
        )
        self.pid = self.repository.replace("/", "-")
        self.bid = f"{self.repository.replace('/', '-')}-{self.commit_hash[:12]}"

    def __clone_repo(self, workdir: str) -> pygit2.Repository:
        logging.debug(f"Cloning {self.clone_url} to {workdir}")

        # TODO: deal with parallelism (multiple cli processes running at the same time)
        repo: pygit2.Repository = pygit2.clone_repository(self.clone_url, workdir)

        # Set gc.auto to 0 to avoid "too many open files" bug
        subprocess.run(
            f"git config gc.auto 0",
            cwd=workdir,
            shell=True,
            capture_output=True,
        )

        return repo

    def __set_commit(self, repo: pygit2.Repository, commit: str):
        commit = repo.revparse_single(commit)
        repo.checkout_tree(commit)
        repo.create_tag(
            str(uuid.uuid4()),
            commit.oid,
            pygit2.GIT_OBJ_COMMIT,
            commit.author,
            commit.message,
        )
        repo.set_head(commit.oid)

    def __checkout_buggy(self, repo: pygit2.Repository) -> None:
        # Checkout the buggy version
        logging.debug(f"Checking out buggy version of {self.bid}")
        self.__set_commit(repo, self.previous_commit_hash)

        # We only apply the non code patch when the bug patch is non-empty
        # Otherwise, we are testing the non code patch alone
        if len(self.non_code_patch) > 0 and len(self.bug_patch) > 0:
            logging.debug(f"Applying non-code patch")
            repo.apply(pygit2.Diff.parse_diff(str(self.non_code_patch)))

        # We apply the test patch when the test patch is non-empty
        if len(self.test_patch) > 0:
            logging.debug(f"Applying test patch")
            repo.apply(pygit2.Diff.parse_diff(str(self.test_patch)))

    def __checkout_fixed(self, repo: pygit2.Repository) -> None:
        # Checkout the fixed version
        logging.debug(f"Checking out fixed version of {self.bid}")
        self.__set_commit(repo, self.commit_hash)

    def checkout(self, workdir: str, fixed: bool = False) -> None:
        """
        Checkout the bug to the given workdir.
        """
        # Clone the repository
        logging.debug(f"Checking out {self.bid} to {workdir}")
        repo = self.__clone_repo(workdir)

        # Checkout the buggy or fixed version
        if fixed:
            self.__checkout_fixed(repo)
        else:
            self.__checkout_buggy(repo)

        subprocess.run(
            f"git remote set-url origin https://github.com/{self.repository}",
            cwd=workdir,
            shell=True,
            capture_output=True,
        )

        # Remove all workflows
        workflows_dir = Path(workdir, ".github", "workflows")
        workflows = list(workflows_dir.glob("*.yml")) + list(
            workflows_dir.glob("*.yaml")
        )
        for workflow in workflows:
            workflow.unlink()
        diff_folder_path = Path("data", self.pid, self.commit_hash)
        self.__create_replication_workflow(diff_folder_path, repo)

        # Dump bug info to file
        logging.debug(f"Dumping bug info to {workdir}/gitbug.json")
        with Path(workdir, "gitbug.json").open("w") as f:
            bug_info = self.bug_info
            bug_info["fixed"] = fixed
            json.dump(bug_info, f)

    def __create_replication_workflow(
        self, diff_folder_path: str, repo_clone: pygit2.Repository
    ):
        workflow_dir_path = os.path.join(diff_folder_path, "workflow")
        workflow_name = os.listdir(workflow_dir_path)[0]
        workflow_path = os.path.join(workflow_dir_path, workflow_name)

        github_actions_path = os.path.join(repo_clone.workdir, ".github", "workflows")
        if not os.path.exists(github_actions_path):
            os.makedirs(github_actions_path)
        new_workflow_path = os.path.join(
            github_actions_path, str(uuid.uuid4()) + ".yml"
        )
        shutil.copyfile(workflow_path, new_workflow_path)

    def __get_diff_path(self, diff_folder_path):
        for path in os.listdir(diff_folder_path):
            if path != "workflow":
                return os.path.join(diff_folder_path, path)

    def run(
        self, workdir: str, output: str, act_cache_dir: Optional[str] = None
    ) -> bool:
        # Check if the workdir has a bug
        logging.debug(f"Running {self.bid} in {workdir}")

        if not Path(workdir, "gitbug.json").exists():
            raise ValueError(f"Workdir {workdir} does not contain a GitBug-Java bug")
        # Read the bug info from the workdir
        with Path(workdir, "gitbug.json").open("r") as f:
            bug_info = json.load(f)
            bug = Bug(bug_info)

        repo = pygit2.Repository(Path(workdir, ".git"))
        docker_client = docker.from_env()

        # Run Actions
        acquire_act_cache = act_cache_dir is None
        if acquire_act_cache:
            act_cache_dir = ActCacheDirManager.acquire_act_cache_dir()
        try:
            logging.debug(f"Creating docker image for {self.bid}")
            base_image = f"gitbug-java:base"
            runner_image = f"gitbug-java:{str(uuid.uuid4())}"

            diff_folder_path = Path("data", self.pid, self.commit_hash)
            create_diff_image(
                base_image, runner_image, self.__get_diff_path(diff_folder_path)
            )

            # TODO: use a hardcoded path to act
            executor = TestExecutor(
                repo_clone=repo,
                language=bug.language,
                act_cache_dir=act_cache_dir,
                default_actions=None,
                runner_image=runner_image,
            )

            logging.debug(f"Executing GitHub Actions for {self.bid}")
            shutil.rmtree(Path(workdir, ".act-result"), ignore_errors=True)
            runs = executor.run_tests(keep_containers=False, offline=True)
            docker_client.images.remove(runner_image, force=True)
        finally:
            shutil.rmtree(Path(workdir, ".act-result"), ignore_errors=True)
            if acquire_act_cache:
                ActCacheDirManager.return_act_cache_dir(act_cache_dir)

        # Check if the run was successful
        def flat_failed_tests(runs):
            return sum(map(lambda act_run: act_run.failed_tests, runs), [])

        def number_of_tests(runs):
            return sum(map(lambda act_run: len(act_run.tests), runs))

        failed_tests = flat_failed_tests(runs)
        expected_tests = len(bug_info["actions_runs"][2][0]["tests"])

        print(f"Expected number of tests: {expected_tests}")
        print(f"Executed tests: {number_of_tests(runs)}")
        print(f"Passing tests: {number_of_tests(runs) - len(failed_tests)}")
        print(f"Failing tests: {len(failed_tests)}")

        if len(failed_tests) > 0:
            print(f"Failed tests:")
            for failed_test in failed_tests:
                print(f"- {failed_test.classname}#{failed_test.name}")

        output_path = os.path.join(output, f"{self.bid}.json")
        with open(output_path, "w") as f:
            json.dump(
                {
                    "expected_tests": expected_tests,
                    "executed_tests": number_of_tests(runs),
                    "passed_tests": number_of_tests(runs) - len(failed_tests),
                    "failed_tests": [
                        {"classname": test.classname, "name": test.name}
                        for test in failed_tests
                    ],
                },
                f,
            )
        print(f"Report written to {output_path}")

        for run in runs:
            logging.debug(run.stdout)

        sys.exit(
            0
            if (
                len(runs) > 0
                and len(failed_tests) == 0
                and number_of_tests(runs) == expected_tests
            )
            else 1
        )

    def __str__(self) -> str:
        return self.bid
