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

    def test_windows_version_resource_matches_project_version(self) -> None:
        project_root = Path(__file__).resolve().parents[1]
        with (project_root / "pyproject.toml").open("rb") as file:
            version = tomllib.load(file)["project"]["version"]

        parts = [int(part) for part in version.split(".")]
        numeric_version = tuple((parts + [0, 0, 0, 0])[:3] + [0])
        resource = (project_root / "packaging" / "windows_version_info.txt").read_text(
            encoding="utf-8"
        )

        self.assertIn(f"filevers={numeric_version}", resource)
        self.assertIn(f"prodvers={numeric_version}", resource)
        self.assertIn(f'StringStruct("FileVersion", "{version}")', resource)
        self.assertIn(f'StringStruct("ProductVersion", "{version}")', resource)


if __name__ == "__main__":
    unittest.main()
