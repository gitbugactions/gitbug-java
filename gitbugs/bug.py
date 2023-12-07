import uuid
import json
import docker
import pygit2
import subprocess

from pathlib import Path


class Bug(object):
    def __init__(self, bug: dict) -> None:
        for key, value in bug.items():
            setattr(self, key, value)

        self.bug_info = bug
        self.bid = f"{self.repository.replace('/', '-')}-{self.commit_hash[:12]}"

    def __clone_repo(self, work_dir: str) -> pygit2.Repository:
        # TODO: deal with parallelism (multiple cli processes running at the same time)
        repo: pygit2.Repository = pygit2.clone_repository(self.clone_url, work_dir)

        # Set gc.auto to 0 to avoid "too many open files" bug
        subprocess.run(
            f"git config gc.auto 0",
            cwd=work_dir,
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
        self.__set_commit(repo, self.previous_commit_hash)

        # We only apply the non code patch when the bug patch is non-empty
        # Otherwise, we are testing the non code patch alone
        if len(self.non_code_patch) > 0 and len(self.bug_patch) > 0:
            repo.apply(pygit2.Diff.parse_diff(str(self.non_code_patch)))
            return True

        # We apply the test patch
        repo.apply(pygit2.Diff.parse_diff(str(self.test_patch)))

    def __checkout_fixed(self, repo: pygit2.Repository) -> None:
        # Checkout the fixed version
        self.__set_commit(repo, self.commit_hash)

    def checkout(self, workdir: str, fixed: bool = False) -> None:
        """
        Checkout the bug to the given workdir.
        """
        # Clone the repository
        repo = self.__clone_repo(workdir)

        # Checkout the buggy or fixed version
        if fixed:
            self.__checkout_fixed(repo)
        else:
            self.__checkout_buggy(repo)

        # Dump bug info to file
        with Path(workdir, "gitbugs.json").open("w") as f:
            bug_info = self.bug_info
            bug_info["fixed"] = fixed
            json.dump(bug_info, f)

    def run(self, workdir: str) -> bool:
        # Read the bug info from the workdir
        with Path(workdir, "gitbugs.json").open("r") as f:
            bug_info = json.load(f)
            bug = Bug(bug_info)

        repo = pygit2.Repository(Path(workdir, ".git"))
        docker_client = docker.from_env()

        act_cache_dir = ActCacheDirManager.acquire_act_cache_dir()
        try:
            # TODO: load the correct image
            image_name = f"gitbugactions-run-bug:{str(uuid.uuid4())}"
            create_diff_image(
                "gitbugactions:latest", image_name, get_diff_path(diff_folder_path)
            )
            executor = TestExecutor(
                repo,
                bug["language"],
                act_cache_dir,
                get_default_actions(diff_folder_path, repo_clone, bug["language"]),
                runner=image_name,
            )
            runs = executor.run_tests(offline=offline)
            docker_client.images.remove(image_name)
        finally:
            ActCacheDirManager.return_act_cache_dir(act_cache_dir)

    return runs

    def __str__(self) -> str:
        return self.bid
