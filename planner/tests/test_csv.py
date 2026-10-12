"""CSV cleaning tests (no Django needed): python -m unittest planner.tests.test_csv"""
import os
import tempfile
import unittest

from planner.core.stations_csv import CsvFormatError, load_stations

HEADER = "OPIS Truckstop ID,Truckstop Name,Address,City,State,Rack ID,Retail Price\n"


def write(body):
    fh = tempfile.NamedTemporaryFile("w", suffix=".csv", delete=False, encoding="utf-8")
    fh.write(HEADER + body)
    fh.close()
    return fh.name


class StationsCsvTests(unittest.TestCase):
    def test_cleaning_rules(self):
        path = write(
            '1,PILOT #1,"I-8, EXIT 1",Gila Bend,AZ,9,3.899\n'
            '1,PILOT TRAVEL CENTER #1,"I-8, EXIT 1",Gila Bend,AZ,9,3.699\n'   # same station, cheaper row
            '2,MAPLE STOP,"HWY 401",Toronto,ON,9,4.100\n'                      # Canada: dropped
            '3,BAD PRICE,"I-70",Salina,KS,9,abc\n'                             # unparsable: dropped
            "4,KWIK TRIP,\"I-94, EXIT 143\",Tomah,WI,9,3.28733333\n"
        )
        try:
            records, stats = load_stations(path)
        finally:
            os.unlink(path)
        by_id = {r["opis_id"]: r for r in records}
        self.assertEqual(sorted(by_id), ["1", "4"])
        self.assertEqual(by_id["1"]["price"], 3.699)       # cheapest row wins
        self.assertEqual(by_id["4"]["price"], 3.28733)     # rounded to 5 decimals
        self.assertEqual((stats["non_us"], stats["bad_price"], stats["stations"]), (1, 1, 2))

    def test_missing_column_is_reported(self):
        fh = tempfile.NamedTemporaryFile("w", suffix=".csv", delete=False)
        fh.write("Name,City\nx,y\n")
        fh.close()
        try:
            with self.assertRaises(CsvFormatError):
                load_stations(fh.name)
        finally:
            os.unlink(fh.name)


if __name__ == "__main__":
    unittest.main()
