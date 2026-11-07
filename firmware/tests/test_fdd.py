"""Exercise the production FDD state machine with simulated head/sensor behavior."""
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]

class FddTest(unittest.TestCase):
    def test_state_machine(self):
        with tempfile.TemporaryDirectory(prefix="surrklank-fdd-") as directory:
            binary = Path(directory) / "fdd-test"
            subprocess.run(["c++", "-std=c++17", "-Wall", "-Wextra", "-Werror", "-I", str(ROOT / "include"),
                            str(ROOT / "src/fdd_engine.cpp"), str(ROOT / "tests/fdd_engine_test.cpp"), "-o", str(binary)], check=True)
            subprocess.run([str(binary)], check=True)

if __name__ == "__main__":
    unittest.main()
