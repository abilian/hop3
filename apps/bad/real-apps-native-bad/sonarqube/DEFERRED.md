# SonarQube (native) — Deferred

**Status:** deferred from the 0.5 test suite.
**Moved:** 2026-04-13

## Blocker

SonarQube 26.x bundles Elasticsearch 8.19 (forked as OpenSearch).
On startup, ES logs show:

```
ERROR app[][o.s.a.p.EsManagedProcess] Failed to check status
ElasticsearchException[Failed to parse info response. Check logs for
  detailed information - Unsupported Content-Type: text/html]
...
Caused by: org.elasticsearch.common.util.concurrent.
  EsRejectedExecutionException: master service is in state [STOPPED]
org.elasticsearch.node.NodeClosedException: node closed
ERROR: Elasticsearch died while starting up, with exit code 1
```

Root causes (combined):
1. Bundled ES requires `vm.max_map_count >= 262144` at the kernel
   level. The workaround `sonar.search.javaAdditionalOpts=-Dnode.
   store.allow_mmap=false` we set isn't sufficient in ES 8.19.
2. Heap allocation may be insufficient under default settings on
   servers that are already busy.
3. Start-timeout of 360s isn't enough — cold ES starts and index
   creation can take 5-10 min, but the app goes into a
   "restarting/dead" loop before then.

## Unblocker for 0.6 (or later)

- Set `vm.max_map_count=262144` at the kernel level (installer
  step, root-only) — this is a real PaaS-level config, not
  app-level.
- Increase `SONAR_CE_JAVAOPTS`, `SONAR_WEB_JAVAOPTS`,
  `SONAR_SEARCH_JAVAOPTS` to reserve enough heap.
- Consider dropping — SonarQube's licensing moved to
  source-available, and lightweight alternatives (semgrep, trivy,
  custom pipelines) cover most use cases.

## How to reintroduce

Move back to `apps/real-apps-native/sonarqube/` once:
1. Hop3 installer applies `vm.max_map_count` sysctl when
   provisioning a server flagged as "supports elasticsearch".
2. A `start-timeout` of 600s+ is acceptable OR the healthcheck
   uses a cheaper path than `/api/system/status`.
