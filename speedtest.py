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

logging.basicConfig(level=logging.DEBUG, format="%(asctime)s %(levelname)-8s %(message)s")
log = logging.getLogger(__name__)


class SpeedtestRunner:
    """Runs Ookla speedtest and writes results to InfulxDB."""

    def __init__(self, influx_url="http://localhost:8086", token=None):
        if token is None:
            token = os.environ.get("DOCKER_INFLUXDB_INIT_ADMIN_TOKEN")

        # initialize influx client
        self.influx_client = InfluxDBClient(url=influx_url, token=token)
        self.influx_org = "my-org"
        self.influx_bucket = "speedtest-bucket"
        self.influx_api = self.influx_client.write_api(write_options=SYNCHRONOUS)

        self.speedtest_proc = None
        signal.signal(signal.SIGINT, self.shutdown)

    def shutdown(self, *args):
        log.info("Shutting Down.")
        if self.speedtest_proc and self.speedtest_proc.poll() is None:
            log.info("Terminating speedtest subprocess.")
            self.speedtest_proc.terminate()
            self.speedtest_proc.wait()
        sys.exit(0)

    def run_speedtest(self):
        # Currently no point in running speedtest if influx is down, maybe store buffer of results
        if not self._is_influx_ready():
            log.error("InfluxDB status check failed.")
            return None

        try:
            log.info("Running speedtest...")
            self.speedtest_proc = subprocess.Popen(
                ["speedtest", "--accept-license", "-f", "json"],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            stdout, stderr = self.speedtest_proc.communicate(timeout=2 * 60)
            if stderr:
                raise subprocess.SubprocessError(stderr)

            return json.loads(stdout)
        except (subprocess.SubprocessError, subprocess.TimeoutExpired) as e:
            log.error(f"Issue getting speedtest results. {e}")
            return None

    def write_results(self, data):
        ts = datetime.fromisoformat(data["timestamp"].replace("Z", "+00:00"))
        measurements = ["ping", "download", "upload", "server"]  # measurements of interest
        log.debug(data)

        if not self._is_influx_ready():
            log.error("InfluxDB status check failed.")
            return

        log.info("Writing speedtest results to InfluxDB.")
        for mem, value in data.items():
            if mem in measurements:
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
            start = time.time()
            res = self.run_speedtest()
            log.debug(f"{res = }")
            if res is None:
                continue

            s.write_results(res)

            elapsed = time.time() - start
            sleep_time = interval - elapsed
            log.debug(f"time taken: {elapsed}")
            log.debug(f"sleep time: {sleep_time}")

            if sleep_time > 0:
                time.sleep(sleep_time)

    def _is_influx_ready(self):
        try:
            log.debug(f"InfluxDB status: {self.influx_client.ready().status}")
            return True
        except urllib3.exceptions.NewConnectionError as e:
            return False

    @staticmethod
    def bps_to_mbps(b):
        """convert bytest per second to Megabits per second"""
        return b * 8 * 1e-6


if __name__ == "__main__":
    if os.environ.get("RUNNING_IN_DOCKER"):
        log.info("Running in Docker.")
        s = SpeedtestRunner(influx_url="http://influx:8086")
    else:
        s = SpeedtestRunner()

    s.run(hours=1)
