# Backup, restore, and rollback

cAdvisor and its proxies are stateless. Preserve the reviewed Compose source, runtime-base lock, both immutable image digests, configuration checksum, Docker socket group mapping, mounted secret-file paths, and release evidence. Do not copy secret values.

Rollback both images as one topology change: verify the previous proxy and cAdvisor digests are pullable, render the previous Compose manifest, apply the three services without rebuilding or deleting volumes, then prove proxy denial tests, cAdvisor health, mTLS metrics, Prometheus target recovery, and absence of public or native exposure.
