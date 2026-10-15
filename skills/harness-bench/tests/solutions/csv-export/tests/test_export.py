import unittest

from app.export import to_csv


class TestExport(unittest.TestCase):
    def test_rows(self):
        self.assertEqual(to_csv([("zone", "flow"), ("north", 3)]), "zone,flow\nnorth,3\n")


if __name__ == "__main__":
    unittest.main()
