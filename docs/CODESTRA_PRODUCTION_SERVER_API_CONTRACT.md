# Codestra cAdvisor Production Server and Native API Contract

## Authority

- Repository: `appolon1908-hue/Codestra-cAdvisor`
- Role: container resource-metrics authority
- Canonical hostname: `cadv.codestra.media`
- Central production host: `37.27.128.39`
- Core host `65.109.65.169`: separate approved exporter installation after central certification
- Status: `SOURCE_CONTRACT_PREPARED_NOT_DEPLOYED`

cAdvisor owns container CPU, memory, I/O, network, OOM, restart, and throttling metrics; controlled container-label policy; image/release evidence; and rollback. It does not own Docker mutation, host metrics, application telemetry, or business actions.

## Native API surface

| Method | Path | Purpose | Boundary |
|---|---|---|---|
| `GET` | `/healthz` | health | private/read-only |
| `GET` | `/metrics` | container resource metrics | private mTLS Prometheus scrape |

Unexpected `404`, `5xx`, public port `8080`, privileged mutation access, writable Docker socket access, or sensitive/high-cardinality labels block production.

## Runtime and label policy

- Native ports remain private.
- Required host mounts are read-only and explicitly reviewed.
- Direct writable Docker socket access is forbidden. A constrained read-only metadata proxy may be used only when source-controlled and tested.
- Privileged mode, host PID, and host network are prohibited unless separately justified and approved; the normal profile uses none of them.
- Store only the allowlisted Codestra labels: business, application, service, environment, region, deployment, and bounded replica identity.
- Customer IDs, users, emails, phones, requests, traces, messages, orders, payments, transaction IDs, container IDs, image IDs, and pod UIDs are not exported as metric labels.

## Production gates

```text
PROTECTED_PRODUCTION_SHA=PASS
READ_ONLY_HOST_MOUNTS=PASS
DOCKER_METADATA_BOUNDARY=PASS
DOCKER_WRITE_AUTHORITY=NO
PRIVILEGED_MODE=NO
HOST_NETWORK=NO
HOST_PID=NO
LABEL_ALLOWLIST=PASS
CARDINALITY_LIMITS=PASS
MTLS_SCRAPE=PASS
IMMUTABLE_IMAGE_DIGEST=PASS
IMAGE_SIGNATURE=PASS
SBOM=PASS
PROVENANCE=PASS
SECRET_SCAN=PASS
ROLLBACK_MANIFEST=PASS
```

## Runtime certification

```text
GET_/healthz=PASS
GET_/metrics=PASS
UNAUTHENTICATED_SCRAPE_DENIED=PASS
MTLS_CLIENT_VERIFY=PASS
CONTAINER_CPU_MEMORY_IO_NETWORK=PASS
OOM_AND_THROTTLING_METRICS=PASS
SENSITIVE_LABELS=0
HIGH_CARDINALITY_LABELS=0
DOCKER_WRITE_TEST=DENIED
UNEXPECTED_404=0
UNEXPECTED_5XX=0
SOURCE_RUNTIME_DRIFT=0
```

## Repository-first remediation

Stop the affected wave and preserve the prior healthy cAdvisor runtime on failure. Fix source/configuration here, add regression tests, commit/push, obtain exact-head CI/review, merge normally, build/sign an immutable image, update the BOM, and retry. Do not patch Compose or mounts only on the server.

## Safety

This document does not deploy cAdvisor or activate scrapes. SSH changes, business writes, communications delivery, provider effects, lending, payments, and trading remain outside scope and disabled.