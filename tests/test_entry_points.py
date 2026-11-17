"""The applications coexist in one interpreter and expose reusable CLI dispatch."""
import contextlib
import io
import unittest

from paperforge.app import main as paperforge
from paperforge.config import load_settings as paperforge_settings
from slotplan.app import main as slotplan
from slotplan.config import load_settings as slotplan_settings


class EntryPointTests(unittest.TestCase):
    def test_both_packages_load_their_own_defaults(self):
        self.assertEqual(paperforge_settings().generation.algorithm, 'auto')
        self.assertGreater(slotplan_settings().schedule.minutes_per_student, 0)

    def test_dispatch_accepts_explicit_arguments(self):
        for command, subcommand in ((paperforge, 'generate'), (slotplan, 'schedule')):
            with self.subTest(command=command.__module__):
                output = io.StringIO()
                with contextlib.redirect_stdout(output), self.assertRaises(SystemExit) as result:
                    command([subcommand, '--help'])
                self.assertEqual(result.exception.code, 0)
                self.assertIn('--config', output.getvalue())
