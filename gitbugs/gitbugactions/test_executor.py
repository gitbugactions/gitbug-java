import subprocess
import os, copy, uuid, pygit2
from gitbugs.gitbugactions.actions.actions import GitHubActions, ActTestsRun
from pygit2 import Repository
from typing import List


class TestExecutor:
    def __init__(
        self,
        repo_clone: Repository,
        language: str,
        act_cache_dir: str,
        default_actions: GitHubActions,
        runner: str = "gitbugactions:latest",
    ):
        self.act_cache_dir = act_cache_dir
        self.repo_clone = repo_clone
        self.runner = runner
        self.language = language
        # Note: these default actions may have different configuration options such as paths, runners, etc.
        self.default_actions = default_actions
        self.first_commit = repo_clone.revparse_single("HEAD")

    def run_tests(
        self, keep_containers: bool = False, offline: bool = False
    ) -> List[ActTestsRun]:
        act_runs: List[ActTestsRun] = []
        default_actions = False

        print("initializing github actions")

        test_actions = GitHubActions(
            self.repo_clone.workdir,
            self.language,
            keep_containers=keep_containers,
            runner=self.runner,
            offline=offline,
        )

        print("done initializing github actions")
        if len(test_actions.test_workflows) == 0 and self.default_actions is not None:
            default_actions = True
            for workflow in self.default_actions.test_workflows:
                new_workflow = copy.copy(workflow)
                new_workflow.path = os.path.join(
                    self.repo_clone.workdir,
                    ".github/workflows",
                    os.path.basename(workflow.path),
                )
                test_actions.test_workflows.append(new_workflow)
        # Act creates names for the containers by hashing the content of the workflows
        # To avoid conflicts between threads, we randomize the name
        for workflow in test_actions.test_workflows:
            workflow.doc["name"] = str(uuid.uuid4())
        test_actions.save_workflows()

        for workflow in test_actions.test_workflows:
            print("running workflow")
            act_runs.append(test_actions.run_workflow(workflow, self.act_cache_dir))

        test_actions.delete_workflows()

        for act_run in act_runs:
            act_run.default_actions = default_actions

        return act_runs
