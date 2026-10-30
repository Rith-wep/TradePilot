import re
import unittest
from pathlib import Path


class PhaseDocumentationTests(unittest.TestCase):
    def test_every_phase_report_is_indexed_and_every_index_link_exists(self) -> None:
        repository = Path(__file__).parents[2]
        phase_directory = repository / "docs" / "phases"
        index = (repository / "docs" / "README.md").read_text(encoding="utf-8")

        report_files = {path.name for path in phase_directory.glob("*.md")}
        indexed_files = set(re.findall(r"\(phases/([^/)]+\.md)\)", index))

        self.assertEqual(indexed_files, report_files)
        for filename in indexed_files:
            self.assertTrue((phase_directory / filename).is_file(), filename)


if __name__ == "__main__":
    unittest.main()
