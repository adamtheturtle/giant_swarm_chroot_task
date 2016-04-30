"""
Tests for ``cli.cli``.
"""

from click.testing import CliRunner

from cli import cli

class TestCreate(object):
    """
    """

    def test_create_task(self):
        runner = CliRunner()
        passed = [
            'createa',
            'http://example.com/foo.tar.gz',
            'echo 1',
        ]
        result = runner.invoke(cli, passed)
        assert result == 0