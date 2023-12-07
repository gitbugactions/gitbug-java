import os, re, xml
import logging
import traceback
import yaml
import shutil
import time
import pygit2
import subprocess
from unidiff import PatchSet
from typing import Optional, List
from gitbugactions.actions.actions import GitHubActions
from gitbugactions.actions.actions import ActCacheDirManager
from gitbugactions.test_executor import TestExecutor
from junitparser.junitparser import JUnitXmlError
from enum import Enum


def delete_repo_clone(repo_clone: pygit2.Repository):
    def retry_remove(function, path, excinfo):
        time.sleep(0.5)
        if os.path.exists(path) and os.path.isdir(path):
            shutil.rmtree(path)
        elif os.path.exists(path) and os.path.isfile(path):
            os.remove(path)

    repo_clone.free()
    if os.path.exists(repo_clone.workdir):
        shutil.rmtree(repo_clone.workdir, onerror=retry_remove)


def clone_repo(clone_url: str, path: str) -> pygit2.Repository:
    retries = 3
    for r in range(retries):
        try:
            repo_clone: pygit2.Repository = pygit2.clone_repository(clone_url, path)
            return repo_clone
        except pygit2.GitError as e:
            if r == retries - 1:
                logging.error(
                    f"Error while cloning {clone_url}: {traceback.format_exc()}"
                )
                raise e


def get_default_github_actions(
    repo_clone: pygit2.Repository, first_commit: pygit2.Commit, language: str
) -> Optional[GitHubActions]:
    act_cache_dir = ActCacheDirManager.acquire_act_cache_dir()
    try:
        head = repo_clone.revparse_single("HEAD")
        # Get commits where workflows were changed by reverse order
        run = subprocess.run(
            f"git log --reverse --diff-filter=AM -- .github/workflows",
            cwd=repo_clone.workdir,
            capture_output=True,
            shell=True,
        )
        stdout = run.stdout.decode("utf-8")
        commits = re.findall("^commit ([a-z0-9]*)", stdout, flags=re.MULTILINE)
        # We add the latest commit because it was the commit used to test
        # the actions in the collect_repos phase
        commits.append(head.hex)

        # Run commits to get first valid workflow
        for commit in commits:
            subprocess.run(
                ["git", "checkout", "-f", commit],
                cwd=repo_clone.workdir,
                capture_output=True,
            )
            try:
                actions = GitHubActions(repo_clone.workdir, language)
                if len(actions.test_workflows) == 1:
                    executor = TestExecutor(
                        repo_clone, language, act_cache_dir, actions
                    )
                    runs = executor.run_tests()
                    # We check for the tests because it is the metric used
                    # to choose the repos that we will run
                    if len(runs[0].tests) > 0:
                        return actions
            except (yaml.YAMLError, JUnitXmlError, xml.etree.ElementTree.ParseError):
                continue
            finally:
                repo_clone.reset(head.oid, pygit2.GIT_RESET_HARD)
                subprocess.run(
                    ["git", "clean", "-f", "-d", "-x"],
                    cwd=repo_clone.workdir,
                    capture_output=True,
                )

        raise RuntimeError(f"{repo_clone.workdir} has no valid default actions.")
    finally:
        ActCacheDirManager.return_act_cache_dir(act_cache_dir)
        repo_clone.reset(first_commit.oid, pygit2.GIT_RESET_HARD)
        if os.path.exists(os.path.join(repo_clone.workdir, ".act-result")):
            shutil.rmtree(os.path.join(repo_clone.workdir, ".act-result"))


class FileType(Enum):
    SOURCE = 0
    TESTS = 1
    NON_SOURCE = 2


def get_file_extension(file_path: str) -> str:
    return file_path.split(".")[-1] if "." in file_path else file_path.split(os.sep)[-1]


def get_patch_file_extensions(patch: PatchSet) -> List[str]:
    return list(
        {get_file_extension(p.source_file) for p in patch}.union(
            {get_file_extension(p.target_file) for p in patch}
        )
    )


def get_file_type(language: str, file_path: str) -> FileType:
    language_extensions = {
        "java": {"java"},
        "python": {"py"},
        "go": {"go"},
    }
    test_keywords = {"test", "tests"}

    if language in ["java", "python"]:
        if any([keyword in file_path.split(os.sep) for keyword in test_keywords]):
            return FileType.TESTS
    elif language in ["go"]:
        if "_test.go" in file_path:
            return FileType.TESTS

    if get_file_extension(file_path) in language_extensions[language]:
        return FileType.SOURCE
    else:
        return FileType.NON_SOURCE
