import os
import tempfile
import unittest
from pathlib import Path
import stat

from process import _is_existing_file

class TestProcess(unittest.TestCase):
    def test_is_existing_file_with_string(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            file_path = os.path.join(tmpdir, "test.txt")

            # Non-existent file
            self.assertFalse(_is_existing_file(file_path))

            # Existing file
            with open(file_path, "w") as f:
                f.write("test")
            self.assertTrue(_is_existing_file(file_path))

            # Directory
            dir_path = os.path.join(tmpdir, "test_dir")
            os.mkdir(dir_path)
            self.assertFalse(_is_existing_file(dir_path))

            # Permission error handling
            forbidden_dir = os.path.join(tmpdir, "forbidden")
            os.mkdir(forbidden_dir)
            os.chmod(forbidden_dir, 0)
            forbidden_file = os.path.join(forbidden_dir, "test.txt")

            self.assertFalse(_is_existing_file(forbidden_file))
            os.chmod(forbidden_dir, stat.S_IRWXU)

    def test_is_existing_file_with_path(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            file_path = Path(tmpdir) / "test.txt"

            # Non-existent file
            self.assertFalse(_is_existing_file(file_path))

            # Existing file
            with open(file_path, "w") as f:
                f.write("test")
            self.assertTrue(_is_existing_file(file_path))

            # Directory
            dir_path = Path(tmpdir) / "test_dir"
            os.mkdir(dir_path)
            self.assertFalse(_is_existing_file(dir_path))

            # Permission error handling
            forbidden_dir = Path(tmpdir) / "forbidden"
            os.mkdir(forbidden_dir)
            os.chmod(forbidden_dir, 0)
            forbidden_file = forbidden_dir / "test.txt"

            self.assertFalse(_is_existing_file(forbidden_file))
            os.chmod(forbidden_dir, stat.S_IRWXU)

if __name__ == '__main__':
    unittest.main()
