# Codestra cAdvisor

This repository is the service authority for container CPU, memory, filesystem, network, I/O, throttling, restart, OOM, lifecycle, and resource-limit telemetry. `appolon1908-hue/Codestra-Prometheus` owns scraping, canonical labels, recording rules, alerts, SLO evaluation, and retention.

## Privilege boundary

cAdvisor requires broad read access to host cgroups, Docker state, devices, and runtime metadata. The container therefore runs privileged, but its root filesystem and all host mounts are read-only, `/tmp` is an isolated no-exec tmpfs, collection is Docker-only, and high-cost process/TCP/scheduler metrics are disabled. This service is host infrastructure and must never share a trust boundary with untrusted workloads.

The runtime suppresses all container labels by default and permits only `com.docker.compose.project` and `com.docker.compose.service`. Environment variables, raw container IDs, customer identifiers, tenant-user identifiers, credentials, and business payload data must never become Prometheus labels.

Each host binds cAdvisor only to its approved private address:

| Server class | Reference private listener |
|---|---|
| Core | `10.40.0.1:8080` |
| Telephony | `10.40.0.2:8080` |
| Provider | `10.40.0.4:8080` |

Port 8080 must be denied on public interfaces and allowed only from the approved Prometheus source. `cadv.codestra.media` is an ownership/DNS identifier; it does not authorize a public Caddy/Kong route or Docker port publication.

## Corporate metric contract

The source-controlled profile covers CPU, memory, network, filesystem, I/O, throttling, OOM, restart, and lifecycle indicators with normalized `codestra_business`, `application`, `service`, `environment`, `deployment`, `region`, and `server` dimensions. Noisy and ephemeral labels are dropped before storage.

See `codestra/enterprise-profile.v1.json` and `codestra/docs/CORPORATE-FEATURES.md` for the corporate feature model.

## Validation

Repository CI renders and inspects `codestra/deploy/compose.candidate.yaml`, proves immutable-image enforcement, read-only Docker API access, mTLS-only metrics exposure, read-only host mounts, label suppression, disabled profiling/high-cost metrics, and the absence of host or public port publication.

A future approved deployment may use:

```bash
cp .env.example .env
# Set accepted image digests, deployment identity, Docker socket GID, and
# external Docker secrets for the proxy certificate, key, and Prometheus CA.
docker compose -f codestra/deploy/compose.candidate.yaml config
docker compose -f codestra/deploy/compose.candidate.yaml up -d
docker compose -f codestra/deploy/compose.candidate.yaml ps
```

The native cAdvisor listener is internal-only. Metrics must be tested through `cadvisor-metrics-proxy:9443` from the observability network with the approved Prometheus client certificate; plaintext or unauthenticated `curl` is not a valid smoke test. These commands are documentation only during the repository-first phase. Before Prometheus target activation, later deployment evidence must prove private-only reachability, expected Docker workloads, absence of environment/tenant labels, bounded sample cardinality, required labels, mTLS scrape success, and rollback.

## Promotion and safety

Promotion is `feature/* -> development -> test -> staging -> production -> main`. Merging changes source authority only and does not deploy. `DEPLOYMENT_ENABLED=NO` remains binding until the 14-repository release manifest is accepted.
