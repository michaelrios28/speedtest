import json
import logging
import os
import subprocess
from datetime import datetime

from influxdb_client import InfluxDBClient, Point, WritePrecision
from influxdb_client.client.write_api import SYNCHRONOUS

logging.basicConfig(level=logging.DEBUG, format="%(levelname)s %(message)s")
log = logging.getLogger(__name__)


class SpeedtestWriter:
    def __init__(self, influx_url="http://localhost:8086", token=None):
        if token is None:
            token = os.environ.get("INFLUXDB_TOKEN")

        # initialize influx client
        client = InfluxDBClient(url=influx_url, token=token)
        self.influx_org = "org"
        self.influx_bucket = "speedtest_results"
        self.influx_api = client.write_api(write_options=SYNCHRONOUS)

    def run_speedtest(self):
        try:
            log.info("Running speedtest.")
            res = subprocess.run(
                ["speedtest", "--accept-license", "-f", "json"],
                input="yes\n".encode(),
                timeout=5 * 60,
                capture_output=True,
                check=True,
            )
            res = json.loads(res.stdout)
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as e:
            log.error(f"Issue getting speedtest results. {e}")
            res = None
        finally:
            return res

    def write_results(self, data):
        ts = datetime.fromisoformat(data["timestamp"].replace("Z", "+00:00"))
        measurments = ["ping", "download", "upload", "server"]
        log.debug(data)
        for mem, value in data.items():
            if mem in measurments:
                for k, v in value.items():
                    point = Point(mem).field(k, v).time(ts, WritePrecision.NS)
                    self.influx_api.write(self.influx_bucket, self.influx_org, point)
                    if k == "bandwidth":
                        point = Point(mem).field(f"{k}_mbps", self.bps_to_mbps(v)).time(ts, WritePrecision.NS)
                        self.influx_api.write(self.influx_bucket, self.influx_org, point)

    @staticmethod
    def bps_to_mbps(b):
        """convert bytest per second to Megabits per second"""
        return b * 8 * 1e-6


if __name__ == "__main__":
    s = SpeedtestWriter()
    res = s.run_speedtest()
    if res is not None:
        s.write_results(res)
