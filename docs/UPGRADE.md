# Upgrade procedure

Update cAdvisor only on a feature branch. Resolve the official release image to an OCI digest, record the full upstream tag commit and binary revision readback, update the cAdvisor build manifest and runtime-base lock together, and rebuild both repository images with the same protected source SHA.

Promote the certified lineage through development, test, staging, production, and main. Staging must prove read-only Docker API behavior, denied mutations and upgrades, bounded labels, private mTLS metrics, restart recovery, and a two-image rollback rehearsal before production authorization.

The parent-repository whitespace gate excludes the byte-preserved `upstream/`
snapshot because official documentation contains literal conflict-marker examples.
That exclusion is bounded by an independent `HEAD:upstream` Git-tree comparison
against `CODESTRA_UPSTREAM_LOCK.json#imported_tree_sha`. A mismatch blocks release;
rollback restores the last protected source and lock together.
