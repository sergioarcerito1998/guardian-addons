ARG BUILD_FROM
FROM $BUILD_FROM

RUN apk add --no-cache python3

WORKDIR /app

COPY guardian_connector.py /app/connector/guardian_connector.py
COPY guardian_sync.py /app/connector/guardian_sync.py
COPY sync_pipeline.py /app/connector/sync_pipeline.py

RUN touch /app/connector/__init__.py

COPY run.sh /run.sh
RUN chmod a+x /run.sh

WORKDIR /app

CMD ["/run.sh"]
