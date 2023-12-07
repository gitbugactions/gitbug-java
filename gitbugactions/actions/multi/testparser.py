from abc import ABC, abstractmethod
from pathlib import Path


class TestParser(ABC):
    @abstractmethod
    def _get_test_results(self, file: Path) -> list:
        """Returns a list of failed tests from a test results file"""
        pass

    def get_test_results(self, filename: str) -> list:
        """Iterates over all files in a directory recursively and returns the aggregated list of test files"""
        tests = []
        file = Path(filename)

        if file.is_dir():
            # Iterate over all files in the directory
            for child in file.iterdir():
                tests.extend(self.get_test_results(str(child)))
        elif file.exists():
            tests.extend(self._get_test_results(file))

        return tests
