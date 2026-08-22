from pathlib import Path
import tomllib
import unittest

import gyrofix


class MetadataTests(unittest.TestCase):
    def test_package_and_project_versions_match(self) -> None:
        project_file = Path(__file__).resolve().parents[1] / "pyproject.toml"
        with project_file.open("rb") as file:
            project = tomllib.load(file)

        self.assertEqual(project["project"]["version"], gyrofix.__version__)


if __name__ == "__main__":
    unittest.main()
