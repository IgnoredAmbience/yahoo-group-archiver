FROM python:3.8.0-alpine3.10

COPY . /yga
WORKDIR /yga

RUN apk add rsync

RUN pip3 install -r requirements.txt

ENV DOWNLOADER="Not_The_Googlebot"
ENV CONCURRENT_ITEMS="1"

ENTRYPOINT run-pipeline3 ./pipeline.py "$DOWNLOADER" --address 0.0.0.0 --concurrent "$CONCURRENT_ITEMS"
