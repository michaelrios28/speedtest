import json
import logging
import os
import signal
import subprocess
import sys
import time
from datetime import datetime

import urllib3.exceptions
from influxdb_client import InfluxDBClient, Point, WritePrecision
from influxdb_client.client.write_api import SYNCHRONOUS

logging.basicConfig(level=logging.DEBUG, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)


class SpeedtestWriter:
    def __init__(self, influx_url="http://localhost:8086", token=None):
        if token is None:
            token = os.environ.get("INFLUXDB_TOKEN")

        # initialize influx client
        self.influx_client = InfluxDBClient(url=influx_url, token=token)
        self.influx_org = "org"
        self.influx_bucket = "speedtest_results"
        self.influx_api = self.influx_client.write_api(write_options=SYNCHRONOUS)

        signal.signal(signal.SIGINT, self.shutdown)

    def shutdown(self, *args):
        log.info("Shutting Down.")
        sys.exit(0)

    def run_speedtest(self):
        # Currently no point in running speedtest if influx is down, maybe store buffer of results
        if not self._is_influx_ready():
            log.error("InfluxDB status check failed.")
            return None

        try:
            log.info("Running speedtest...")
            self.p = subprocess.run(
                ["speedtest", "--accept-license", "-f", "json"],
                input="yes\n".encode(),
                timeout=5 * 60,
                capture_output=True,
                check=True,
            )
            return json.loads(self.p.stdout)
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as e:
            log.error(f"Issue getting speedtest results. {e}")
            return None

    def write_results(self, data):
        ts = datetime.fromisoformat(data["timestamp"].replace("Z", "+00:00"))
        measurments = ["ping", "download", "upload", "server"]
        log.debug(data)

        if not self._is_influx_ready():
            log.error("InfluxDB status check failed.")
            return

        for mem, value in data.items():
            if mem in measurments:
                for k, v in value.items():
                    point = Point(mem).field(k, v).time(ts, WritePrecision.NS)
                    self.influx_api.write(self.influx_bucket, self.influx_org, point)
                    if k == "bandwidth":
                        point = Point(mem).field(f"{k}_mbps", self.bps_to_mbps(v)).time(ts, WritePrecision.NS)
                        self.influx_api.write(self.influx_bucket, self.influx_org, point)

    def run(self, weeks=0, days=0, hours=0, minutes=0):
        interval = (weeks * 604800) + (days * 86400) + (hours * 3600) + (minutes * 60)
        log.info(f"Running w/ interval of {interval} seconds.")

        while True:
            res = self.run_speedtest()
            if res is not None:
                s.write_results(res)
            time.sleep(interval)

    def _is_influx_ready(self):
        try:
            log.info(f"InfluxDB status: {self.influx_client.ready().status}")
            return True
        except urllib3.exceptions.NewConnectionError as e:
            return False

    @staticmethod
    def bps_to_mbps(b):
        """convert bytest per second to Megabits per second"""
        return b * 8 * 1e-6


if __name__ == "__main__":
    s = SpeedtestWriter()
    s.run(minutes=1)
