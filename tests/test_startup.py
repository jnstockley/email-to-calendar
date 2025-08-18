from unittest import TestCase

from src.main import main


class TestStartup(TestCase):
    def test_startup(self):
        main()
        assert True
