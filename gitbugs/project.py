from gitbugs.bug import Bug
from typing import Optional


class Project(object):
    def __init__(self, pid: str) -> None:
        self.pid = pid
        self.bugs = {}

    def add_bug(self, bug: Bug) -> None:
        self.bugs[bug.bid] = bug

    def get_bug(self, bid: str) -> Optional[Bug]:
        return self.bugs[bid]

    def get_bugs(self) -> list:
        return list(self.bugs.values())

    def __str__(self) -> str:
        return self.name
