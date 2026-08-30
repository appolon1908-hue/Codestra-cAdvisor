# Repository Authority

Canonical service hostname: `cadv.codestra.media`
Canonical DNS A target: `37.27.128.39`
DNS TTL: `600`

This repository is the principal source authority for the Codestra cAdvisor deployment/configuration. Do not introduce alternate public hostnames or legacy domain names in configuration, documentation, examples, health checks, or deployment manifests.

Exposure policy: PRIVATE. DNS may resolve publicly, but the cAdvisor service/metrics port must be reachable only from approved monitoring/private networks. Do not expose the native cAdvisor endpoint directly to the public Internet.

Upstream/downstream: cAdvisor exposes container metrics -> Prometheus (`prom.codestra.media`) scrapes them -> Grafana (`graf.codestra.media`) visualizes them -> Alertmanager (`aler.codestra.media`) receives alerts derived from Prometheus rules.

Persistent branch model: `main`, `development`, `test`, `staging`, `production`. Temporary branches: `feature/*`, `fix/*`, `upgrade/*`, `security/*`, `docs/*`, `hotfix/*`, `release/*`, `rollback/*`.

Promotion: feature/fix/upgrade/security -> development -> test -> staging -> production -> main. Never make an upstream-version upgrade directly on staging, production, or main.
