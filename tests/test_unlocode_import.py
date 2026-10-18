import csv
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

source=Path(__file__).resolve().parents[1]/"linux-pi"/"installers"/"common"/"import_unlocode_ports.py"
spec=importlib.util.spec_from_file_location("ports", source)
ports=importlib.util.module_from_spec(spec)
spec.loader.exec_module(ports)

class PortImportTests(unittest.TestCase):
    def test_coordinates(self):
        self.assertEqual(ports.parse_coordinates("4515N 06604W"), (45.25, -(66+4/60)))
        with self.assertRaises(ValueError):
            ports.parse_coordinates("4599N 06604W")

    def test_preserve_airports_and_filter_functions(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d)
            original=root/"catalog.json"
            original.write_text(json.dumps([
              {"name":"Existing airport","category":"airport","latitude":45,"longitude":-66}
            ]),encoding="utf-8")
            rows=root/"ports.csv"
            with rows.open("w",encoding="utf-8",newline="") as f:
                writer=csv.DictWriter(f,fieldnames=["Country","Location","Name","Function","Coordinates"])
                writer.writeheader()
                writer.writerow(dict(Country="CA",Location="XYZ",Name="Test Harbour",Function="1------",Coordinates="4515N 06604W"))
                writer.writerow(dict(Country="CA",Location="ABC",Name="Airport Only",Function="-4-----",Coordinates="4515N 06604W"))
            output=root/"out.json"
            self.assertEqual(ports.import_ports(rows,original,output),1)
            data=json.loads(output.read_text(encoding="utf-8"))
            self.assertEqual(len(data),2)
            self.assertEqual(data[0]["locode"],"CAXYZ")
            self.assertEqual(data[1]["name"],"Existing airport")
if __name__=="__main__":
    unittest.main()