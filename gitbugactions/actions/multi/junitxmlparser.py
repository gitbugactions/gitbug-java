from .testparser import TestParser
from junitparser import JUnitXml, TestCase, TestSuite
from typing import List, Union
from pathlib import Path


class JUnitXMLParser(TestParser):
    def __get_test_results_xml(
        self, xml: Union[JUnitXml, TestSuite, TestCase]
    ) -> List[TestCase]:
        """Recursive function to iterate over the JUnit XML file and return a list of tests"""
        tests: List[TestCase] = []

        # Check if the element is a TestCase (leaf node)
        if not isinstance(xml, TestCase):
            # If it is a TestSuite, iterate over all elements
            for element in xml:
                if element is not None:
                    tests.extend(self.__get_test_results_xml(element))
        else:
            tests.append(xml)

        return tests

    def _get_test_results(self, file: Path) -> list:
        """Returns a list of failed tests from a JUnit XML file"""
        tests: List[TestCase] = []

        # Check if it is an xml file
        if file.suffix == ".xml":
            # Load the XML file with the JUnit XML parser
            xml = JUnitXml.fromfile(str(file))
            if xml is not None:
                # Start the recursive function on the root element
                tests.extend(self.__get_test_results_xml(xml))

        return tests
