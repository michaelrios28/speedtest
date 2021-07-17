FROM python:3.9.6-buster

WORKDIR /src

ENV INFLUXDB_TOKEN=${INFLUXDB_TOKEN}

COPY speedtest.py ./
COPY requirements.txt ./

RUN apt update && curl -s https://install.speedtest.net/app/cli/install.deb.sh | bash && apt install speedtest

RUN pip install -r requirements.txt