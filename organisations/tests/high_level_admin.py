"""Tests for higher level admin functions such as creating clubs"""
from tests.test_manager import CobaltTestManager


class OrgHighLevelAdmin:
    """Admin functions"""

    def __init__(self, manager: CobaltTestManager):
        self.manager = manager
        self.client = self.manager.client
