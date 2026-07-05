ARG BUILD_FROM
FROM $BUILD_FROM

RUN apk add --no-cache python3

WORKDIR /app

COPY guardian_connector.py /app/guardian_connector.py
COPY run.sh /run.sh

RUN chmod a+x /run.sh

CMD ["/run.sh"]
