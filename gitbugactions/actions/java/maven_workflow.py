from typing import List
from junitparser import TestCase
from pathlib import Path
import re

from gitbugactions.actions.workflow import GitHubWorkflow
from gitbugactions.actions.multi.junitxmlparser import JUnitXMLParser


class MavenWorkflow(GitHubWorkflow):
    BUILD_TOOL_KEYWORDS = ["maven", "mvn", "mavenw", "mvnw"]
    # Regex patterns to match maven test commands
    __TESTS_COMMAND_PATTERNS = [
        r"(maven|mvn|mavenw|mvnw)\s+(([^\s]+\s+)*)?(test|package|verify|install)",
    ]

    def _is_test_command(self, command) -> bool:
        # Checks if the given command matches any of the tests command patterns
        for pattern in MavenWorkflow.__TESTS_COMMAND_PATTERNS:
            if re.search(pattern, command):
                return True
        return False

    def instrument_test_steps(self):
        pass

    def get_test_results(self, repo_path) -> List[TestCase]:
        parser = JUnitXMLParser()
        return parser.get_test_results(
            str(Path(repo_path, "target", "surefire-reports"))
        )

    def get_build_tool(self) -> str:
        return "maven"
