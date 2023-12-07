import os, tempfile, shutil, traceback
import grp
import uuid
import time
import docker
import logging
import subprocess
import threading
from pathlib import Path

from typing import List, Dict, Set
from junitparser import TestCase, Error
from dataclasses import dataclass
from gitbugs.gitbugactions.actions.workflow import GitHubWorkflow, GitHubWorkflowFactory
from gitbugs.gitbugactions.github_token import GithubToken
from gitbugs.gitbugactions.actions.action import Action


class ActCacheDirManager:
    # We need to set a different cache dir for each worker to avoid conflicts
    # See https://github.com/nektos/act/issues/1885 -> "act's git actions download cache isn't process / thread safe"

    __ACT_CACHE_DIR_LOCK: threading.Lock = threading.Lock()
    __ACT_CACHE_DIRS: Dict[str, bool] = dict()
    __DEFAULT_CACHE_DIR: str = os.path.join(
        tempfile.gettempdir(), "act-cache", "default"
    )

    @classmethod
    def init_act_cache_dirs(cls, n_dirs: int):
        with cls.__ACT_CACHE_DIR_LOCK:
            # Generate the directories
            cls.__ACT_CACHE_DIRS = {
                os.path.join(
                    tempfile.gettempdir(), "act-cache", str(uuid.uuid4())
                ): True
                for _ in range(n_dirs)
            }

            # Create the directories
            for cache_dir in cls.__ACT_CACHE_DIRS:
                if not os.path.exists(cache_dir):
                    os.makedirs(os.path.join(cache_dir, "act"))
            if not os.path.exists(cls.__DEFAULT_CACHE_DIR):
                os.makedirs(cls.__DEFAULT_CACHE_DIR)

    @classmethod
    def acquire_act_cache_dir(cls) -> str:
        """
        A thread calls this method to acquire a free act cache dir from the queue
        """
        cls.__ACT_CACHE_DIR_LOCK.acquire()

        try:
            if len(cls.__ACT_CACHE_DIRS) == 0:
                logging.warning(
                    f"Using a default act cache dir. If running multiple threads you must use different act caches for each thread."
                )
                return cls.__DEFAULT_CACHE_DIR

            for cache_dir in cls.__ACT_CACHE_DIRS:
                if cls.__ACT_CACHE_DIRS[cache_dir]:
                    cls.__ACT_CACHE_DIRS[cache_dir] = False
                    return cache_dir

            logging.warning(f"No act cache dir is available. Using a random one...")

            return os.path.join(tempfile.gettempdir(), "act-cache", str(uuid.uuid4()))
        finally:
            cls.__ACT_CACHE_DIR_LOCK.release()

    @classmethod
    def return_act_cache_dir(cls, act_cache_dir: str):
        """
        A thread calls this method to return and free up the acquired act cache dir
        """
        cls.__ACT_CACHE_DIR_LOCK.acquire()

        try:
            # If the default cache dir, do nothing
            if act_cache_dir == cls.__DEFAULT_CACHE_DIR:
                return
            # If a managed one, make it free
            elif act_cache_dir in cls.__ACT_CACHE_DIRS:
                cls.__ACT_CACHE_DIRS[act_cache_dir] = True
                return
            # If a random one delete it
            elif os.path.exists(act_cache_dir):
                shutil.rmtree(act_cache_dir, ignore_errors=True)
                return
        finally:
            cls.__ACT_CACHE_DIR_LOCK.release()

    @classmethod
    def cache_action(cls, action: Action):
        """
        Downloads an action to the base cache dir and creates a symlink to it in every act cache dir
        Note: because every action is unique, we do not need locks here
        """
        try:
            # Download the action to the base cache dir
            # The name of the diretory is in the format <org>-<repo>@<ref>
            action_dir_name = f"{action.org}-{action.repo}@{action.ref}"
            action_dir = os.path.join(cls.__DEFAULT_CACHE_DIR, action_dir_name)
            action.download(action_dir)

            # Create a symlink to the action in every act cache dir
            for cache_dir in cls.__ACT_CACHE_DIRS:
                os.symlink(action_dir, os.path.join(cache_dir, "act", action_dir_name))
        except Exception:
            logging.error(
                f"Error while caching action {action.declaration}: {traceback.format_exc()}"
            )


@dataclass
class ActTestsRun:
    failed: bool
    tests: List[TestCase]
    stdout: str
    stderr: str
    workflow: GitHubWorkflow
    workflow_name: str
    build_tool: str
    elapsed_time: int
    default_actions: bool

    @property
    def failed_tests(self) -> List[TestCase]:
        failed_tests = []
        for test in self.tests:
            # Check if it is failed (not passed, not skipped and without errors)
            if (
                not test.is_passed
                and not test.is_skipped
                and not any(map(lambda r: isinstance(r, Error), test.result))
            ):
                failed_tests.append(test)
        return failed_tests

    @property
    def erroring_tests(self) -> List[TestCase]:
        erroring_tests = []
        for test in self.tests:
            # Check if it is erroring (not passed, not skipped, and with erorrs)
            if any(map(lambda r: isinstance(r, Error), test.result)):
                erroring_tests.append(test)
        return erroring_tests

    def asdict(self) -> Dict:
        res = {}

        for k, v in self.__dict__.items():
            if k == "tests":
                res[k] = []
                for test in self.tests:
                    results = []
                    for result in test.result:
                        results.append(
                            {
                                "result": result.__class__.__name__,
                                "message": result.message,
                                "type": result.type,
                            }
                        )
                    if len(results) == 0:
                        results.append({"result": "Passed", "message": "", "type": ""})

                    res[k].append(
                        {
                            "classname": test.classname,
                            "name": test.name,
                            "time": test.time,
                            "results": results,
                            "stdout": test.system_out,
                            "stderr": test.system_err,
                        }
                    )
            elif k == "workflow":
                res[k] = {
                    "path": self.workflow.path,
                    "type": self.workflow.get_build_tool(),
                }
            else:
                res[k] = v

        return res


class Act:
    __ACT_PATH = "act"
    __ACT_SETUP = False
    __FLAGS = f"--pull=false --no-cache-server --max-parallel 1"
    __SETUP_LOCK = threading.Lock()
    __MEMORY_LIMIT = "7g"

    def __init__(
        self,
        base_image: str,
        runner_image: str,
        timeout=5,
        reuse: bool = False,
        offline: bool = False,
    ):
        """
        Args:
            timeout (int): Timeout in minutes
        """
        Act.__setup_act(base_image=base_image, runner_image=runner_image)
        if reuse:
            self.flags = "--reuse"
        else:
            self.flags = "--rm"
        # The flag -u allows files to be created with the current user
        self.flags += f" --container-options '-u {os.getuid()}:{os.getgid()}"
        if offline:
            self.flags += " --network none"
        self.flags += f" --memory={Act.__MEMORY_LIMIT}"
        self.flags += "'"

        self.__DEFAULT_RUNNERS = f"-P ubuntu-latest={runner_image}"
        self.timeout = timeout

    @staticmethod
    def __setup_act(base_image: str, runner_image: str):
        with Act.__SETUP_LOCK:
            if Act.__ACT_SETUP:
                return
            # Checks act installation
            run = subprocess.run(
                f"{Act.__ACT_PATH} --help", shell=True, capture_output=True
            )
            if run.returncode != 0:
                logging.error("Act is not correctly installed")
                exit(-1)

            # Checks that base image exists
            client = docker.from_env()
            if len(client.images.list(name=base_image)) != 1:
                logging.error(f"Base image {base_image} does not exist")
                exit(-1)

            # Removes runner image if exists
            if len(client.images.list(name=runner_image)) > 0:
                client.images.remove(image=runner_image, force=True)

            # Write a Dockerfile to a temporary directory and build the runner image
            tmp_dir = tempfile.mkdtemp()
            Path(tmp_dir).mkdir(parents=True, exist_ok=True)
            dockerfile_path = Path(tmp_dir, "Dockerfile")
            with dockerfile_path.open("w") as f:
                client = docker.from_env()
                dockerfile = f"FROM {base_image}\n"
                dockerfile += f"RUN sudo groupadd -o -g {os.getgid()} {grp.getgrgid(os.getgid()).gr_name}\n"
                dockerfile += f"RUN sudo usermod -G {os.getgid()} runner\n"
                dockerfile += f"RUN sudo usermod -u {os.getuid()} runner\n"
                f.write(dockerfile)

            client.images.build(path=tmp_dir, tag=runner_image, forcerm=True)
            shutil.rmtree(tmp_dir, ignore_errors=True)
            Act.__ACT_SETUP = True

    @staticmethod
    def set_memory_limit(limit: str):
        Act.__MEMORY_LIMIT = limit

    def run_act(
        self, repo_path, workflow: GitHubWorkflow, act_cache_dir: str
    ) -> ActTestsRun:
        command = f"cd {repo_path}; "
        command += f"ACT_DISABLE_VERSION_CHECK=1 XDG_CACHE_HOME='{act_cache_dir}' timeout {self.timeout * 60} {Act.__ACT_PATH} {self.__DEFAULT_RUNNERS} {Act.__FLAGS} {self.flags}"
        if GithubToken.has_tokens():
            token: GithubToken = GithubToken.get_token()
            command += f" -s GITHUB_TOKEN={token.token}"
        command += f" -W {workflow.path}"

        start_time = time.time()
        run = subprocess.run(command, shell=True, capture_output=True)
        end_time = time.time()

        stdout = run.stdout.decode("utf-8")
        stderr = run.stderr.decode("utf-8")

        # TODO: make this work without the bind option
        tests = workflow.get_test_results(
            os.path.join(
                repo_path, ".act-result", os.path.basename(os.path.normpath(repo_path))
            )
        )

        tests_run = ActTestsRun(
            failed=False,
            tests=tests,
            stdout=stdout,
            stderr=stderr,
            workflow=workflow,
            workflow_name=workflow.doc["name"],
            build_tool=workflow.get_build_tool(),
            elapsed_time=end_time - start_time,
            default_actions=False,
        )

        if (
            # Failed run with failed tests but with memory limit exceed should not
            # be considered. We do not check the return code because act does not
            # pass the code from the container.
            run.returncode == 1  # Increase performance by avoiding
            and len(tests_run.failed_tests) != 0  # to check the output in every run
            and ("exitcode '137'" in stderr or "exitcode '137': failure" in stdout)
        ) or (
            # 124 is the return code for the timeout
            (run.returncode == 124)
            or (len(tests_run.failed_tests) == 0 and run.returncode != 0)
            or len(tests_run.erroring_tests) > 0
        ):
            tests_run.failed = True
            logging.warning(f"RETURN CODE: {run.returncode}")

        updated_tokens = set()
        if GithubToken.has_tokens():
            token.update_rate_limit()
            updated_tokens.add(token.token)
            for token in workflow.tokens:
                if token.token not in updated_tokens:
                    token.update_rate_limit()

        return tests_run


class GitHubActions:
    """
    Class to handle GitHub Actions
    """

    def __init__(
        self,
        repo_path,
        language: str,
        base_image: str,
        runner_image: str,
        keep_containers: bool = False,
        offline: bool = False,
    ):
        self.repo_path = repo_path
        self.keep_containers = keep_containers
        self.language: str = language.strip().lower()
        self.workflows: List[GitHubWorkflow] = []
        self.test_workflows: List[GitHubWorkflow] = []
        self.base_image = base_image
        self.runner_image = runner_image
        self.offline = offline

        workflows_path = os.path.join(repo_path, ".github", "workflows")
        for dirpath, dirnames, filenames in os.walk(workflows_path):
            yaml_files = list(
                filter(
                    lambda file: file.endswith(".yml") or file.endswith(".yaml"),
                    filenames,
                )
            )
            for file in yaml_files:
                # Create workflow object according to the language and build system
                workflow: GitHubWorkflow = GitHubWorkflowFactory.create_workflow(
                    os.path.join(dirpath, file), self.language
                )

                self.workflows.append(workflow)
                if not workflow.has_tests() or workflow.has_matrix_include_exclude():
                    continue

                workflow.instrument_os()
                workflow.instrument_on_events()
                workflow.instrument_strategy()
                workflow.instrument_jobs()
                workflow.instrument_cache_steps()
                workflow.instrument_setup_steps()
                workflow.instrument_test_steps()

                filename = os.path.basename(workflow.path)
                dirpath = os.path.dirname(workflow.path)
                new_filename = (
                    filename.split(".")[0] + "-crawler." + filename.split(".")[1]
                )
                new_path = os.path.join(dirpath, new_filename)
                workflow.path = new_path

                self.test_workflows.append(workflow)

    def get_actions(self) -> Set[Action]:
        actions: Set[Action] = set()
        for workflow in self.test_workflows:
            actions.update(workflow.get_actions())
        return actions

    def save_workflows(self):
        for workflow in self.test_workflows:
            if not os.path.exists(os.path.dirname(workflow.path)):
                os.makedirs(os.path.dirname(workflow.path))
            workflow.save_yaml(workflow.path)

    def delete_workflow(self, workflow):
        if os.path.exists(workflow.path):
            os.remove(workflow.path)

    def remove_workflow(self, rem_workflow):
        for i, workflow in enumerate(self.test_workflows):
            if rem_workflow.path == workflow.path:
                self.test_workflows.pop(i)
                self.delete_workflow(workflow)
                break

    def delete_workflows(self):
        for workflow in self.test_workflows:
            self.delete_workflow(workflow)

    def run_workflow(self, workflow, act_cache_dir: str) -> ActTestsRun:
        act = Act(
            base_image=self.base_image,
            runner_image=self.runner_image,
            timeout=10,
            reuse=self.keep_containers,
            offline=self.offline,
        )
        return act.run_act(self.repo_path, workflow, act_cache_dir=act_cache_dir)

    def remove_containers(self):
        client = docker.from_env()
        ancestors = [
            "gitbugactions:latest",
        ]

        for container in client.containers.list(filters={"ancestor": ancestors}):
            container.stop()
            container.remove(v=True, force=True)
