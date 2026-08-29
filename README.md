# Codestra cAdvisor

This repository is the service authority for container CPU, memory, filesystem, network, OOM, and resource-limit metrics. `appolon1908-hue/Codestra-Prometheus` owns scraping, labels, recording rules, alerts, and retention.

## Privilege boundary

cAdvisor requires broad read access to host cgroups, Docker state, devices, and the Docker socket. The container therefore runs privileged, but its root filesystem and all host mounts are read-only and `/tmp` is an isolated tmpfs. This service must be treated as host infrastructure, reviewed separately from application containers, and never share untrusted workloads.

The runtime suppresses all container labels by default and permits only `com.docker.compose.project` and `com.docker.compose.service`. Environment variables, raw container labels, customer identifiers, and tenant identifiers must never become Prometheus labels.

Each host binds cAdvisor only to its private Hetzner vSwitch address:

| Server | Private listener |
|---|---|
| `codestra-core-01` | `10.40.0.1:8080` |
| `codestra-telephony-01` | `10.40.0.2:8080` |
| `codestra-provider-01` | `10.40.0.4:8080` |

Port 8080 must be denied on public interfaces and allowed only from the approved Prometheus source. Do not assign public DNS, add a Caddy/Kong route, or publish the port through Docker.

## Cardinality controls

Only Docker containers are collected. Profiling and expensive process/TCP/scheduler metrics are disabled. Prometheus adds `environment`, `server`, `application=infrastructure`, `service=cadvisor`, and `tenant_scope=aggregate`, then strips raw IDs and sensitive labels centrally.

## Validation

```bash
cp .env.example .env
# Set the reviewed digest and this host's private IP.
docker compose -f deploy/compose.yaml config
docker compose -f deploy/compose.yaml up -d
curl --fail http://PRIVATE_IP:8080/metrics
```

Before Prometheus target activation, prove private-only reachability, expected Docker containers, no environment-variable or tenant labels, bounded sample count, a successful scrape with required labels, and rollback. Deployment is a separate approved operation.

Promotion is `feature/* -> development -> test -> staging -> production -> main`. Merging does not deploy.
