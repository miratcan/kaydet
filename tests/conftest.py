from configparser import ConfigParser, SectionProxy
import pytest

from rich.console import Console
from rich.text import Text


class MockConsole(Console):
    """A mock Rich Console to capture printed content."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.printed_text = []

    def print(self, *objects, **kwargs):
        for obj in objects:
            if isinstance(obj, Text):
                self.printed_text.append(obj.markup)
            else:
                self.printed_text.append(str(obj))


@pytest.fixture
def mock_config() -> SectionProxy:
    config = ConfigParser()
    config["SETTINGS"] = {
        "COLOR_HEADER": "bold cyan",
        "COLOR_TAG": "bold magenta",
        "COLOR_DATE": "green",
        "COLOR_ID": "yellow",
    }
    return config["SETTINGS"]


@pytest.fixture
def mock_console() -> MockConsole:
    return MockConsole()