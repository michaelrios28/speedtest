FROM python:3.9.6-buster

WORKDIR /src

ENV RUNNING_IN_DOCKER yes

RUN apt update && curl -s https://install.speedtest.net/app/cli/install.deb.sh | bash && apt install speedtest

COPY requirements.txt ./
COPY speedtest.py ./
COPY wait-for-it.sh ./
RUN pip install -r requirements.txt

CMD [ "python", "speedtest.py" ]