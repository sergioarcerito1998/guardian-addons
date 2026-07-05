ARG BUILD_FROM
FROM $BUILD_FROM

RUN apk add --no-cache python3 py3-pip \
    && pip3 install --no-cache-dir --break-system-packages websocket-client

WORKDIR /app

COPY guardian_connector.py /app/connector/guardian_connector.py
COPY guardian_sync.py /app/connector/guardian_sync.py
COPY sync_pipeline.py /app/connector/sync_pipeline.py
COPY github_transport.py /app/connector/github_transport.py
COPY sync_runtime.py /app/connector/sync_runtime.py
COPY inventory_v2.py /app/connector/inventory_v2.py
COPY privacy_v2.py /app/connector/privacy_v2.py

RUN touch /app/connector/__init__.py

COPY run.sh /run.sh
RUN chmod a+x /run.sh

WORKDIR /app

CMD ["/run.sh"]
