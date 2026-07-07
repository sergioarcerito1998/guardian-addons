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
COPY diagnostic_inventory.py /app/connector/diagnostic_inventory.py
COPY entity_diagnostics.py /app/connector/entity_diagnostics.py
COPY core_diagnostics.py /app/connector/core_diagnostics.py
COPY error_fingerprints.py /app/connector/error_fingerprints.py
COPY diagnostic_history.py /app/connector/diagnostic_history.py
COPY issue_identity.py /app/connector/issue_identity.py
COPY issue_priority.py /app/connector/issue_priority.py
COPY health_report.py /app/connector/health_report.py
COPY health_timeline.py /app/connector/health_timeline.py
COPY action_registry.py /app/connector/action_registry.py
COPY autonomy_runtime.py /app/connector/autonomy_runtime.py
COPY operation_journal.py /app/connector/operation_journal.py
COPY repair_executor.py /app/connector/repair_executor.py
COPY repair_planner.py /app/connector/repair_planner.py
COPY repair_verifier.py /app/connector/repair_verifier.py
COPY safety_policy.py /app/connector/safety_policy.py

RUN python3 -c "import sys; sys.path.insert(0, '/app'); import connector.autonomy_runtime, connector.action_registry, connector.operation_journal, connector.repair_executor, connector.repair_planner, connector.repair_verifier, connector.safety_policy"


RUN touch /app/connector/__init__.py

COPY run.sh /run.sh
RUN chmod a+x /run.sh

WORKDIR /app

CMD ["/run.sh"]
