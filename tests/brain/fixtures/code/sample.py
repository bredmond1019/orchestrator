"""Fixture module for code_chunking tests."""

import os

VERSION = "1.0"


def helper(x):
    return x + 1


class Widget:
    """A widget."""

    def __init__(self, name):
        self.name = name

    def render(self):
        return f"<{self.name}>"
