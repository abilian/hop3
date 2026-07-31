# Migrating from Kubernetes / k3s to Hop3

Thinking about leaving Kubernetes? Maybe you stood up an EKS/GKE/AKS cluster (or a self-hosted k3s) for what turned out to be one web app, a database, and a couple of workers — and you now spend more time on the cluster than on the app. Maybe the control plane bill, the etcd backups, the Ingress controller upgrades, the Helm chart you copied from someone else and never fully understood, and the YAML that grew faster than the code finally tipped the balance. If the cluster was overkill for the real traffic, Hop3 gives you a `git push` deploy on one server you can hold in your head. This guide helps you migrate a Kubernetes or k3s workload to Hop3.

The trade-off is worth stating up front, before you spend an afternoon on it, because it is the whole point. Kubernetes is a multi-node scheduler: it places pods across machines, restarts them when nodes die, scales replicas up and down, and rolls deploys out across a fleet without dropping traffic. Hop3 is a single server. You give up multi-node scheduling, horizontal pod autoscaling, rolling deploys across replicas, and the service mesh entirely. In exchange you get one box to reason about, one predictable bill, and a deploy that is `git push` instead of `kubectl apply` plus a Helm values file plus an Ingress annotation. If your app genuinely needs to run across many nodes — real horizontal scale, node-failure tolerance, a mesh between dozens of services — stay on Kubernetes. The right fit for Hop3 is the very common case: a cluster running what is really a handful of always-on services that one well-sized server would carry comfortably.

## What's Similar

More than you'd expect, once you strip away the control plane. The thing you actually ship — a container, an env-var bundle, a port, a volume — maps cleanly onto Hop3:

| Kubernetes | Hop3 |
|------------|------|
| A `Deployment` | A Hop3 app |
| `kubectl apply -f` / `helm upgrade` | `git push hop3 main` (or `hop3 deploy`) |
| `ConfigMap` / `Secret` | `[env]` + addon credentials |
| `kubectl set env` | `hop3 env set` |
| `kubectl logs -f` | `hop3 app logs` |

The container image you built still builds. The env vars you injected still inject. What disappears is the orchestration layer between you and the box — and on one server you don't need it.

Where Kubernetes drives everything through `kubectl <verb> <resource>`, Hop3 uses space-separated `hop3 <noun> <verb>`, and the app you're targeting is always the `--app` flag rather than a `-n namespace` plus a resource name. So `kubectl set env deployment/web FOO=bar` becomes `hop3 env set FOO=bar --app web`.

There's no automated manifest importer — Hop3 does not read your YAML, Helm charts, or Kustomize overlays. The translation is short and mechanical, though, and the sections below walk through it object by object. (If your app already keeps its process definitions in a `Procfile`, `hop3 app migrate procfile . --dry-run` will scaffold a starting `hop3.toml` from that.)

## What's Different

| Kubernetes | Hop3 |
|------------|------|
| Multi-node cluster + control plane (etcd, scheduler) | Single server, no control plane |
| Horizontal Pod Autoscaler | Manual via `hop3 ps scale` |
| Rolling deploys across replicas | Restart on one host |
| `Service` + `Ingress` + Ingress controller | Automatic nginx, no manifests |
| `StatefulSet` databases, operators | `hop3 addon` (PostgreSQL, MySQL, Redis, S3/MinIO — and growing) |
| Service mesh (Istio, Linkerd) | Apps colocated on one host (localhost) |

Hop3 is simpler. You manage one server instead of a cluster, and most of what Kubernetes asks you to declare — Services, Ingress, the controller that reconciles them — Hop3 just does.

## Step 1: Set Up Your Hop3 Server

Provision a server (Ubuntu 24.04 LTS recommended; Debian, Fedora, and Rocky/Alma also work) and install Hop3:

```bash
ssh root@your-server.com
curl -LsSf https://hop3.cloud/install-server.py | sudo python3 -
```

Install the CLI on your local machine:

```bash
hop3-install cli
```

Connect the CLI to your server. On a first install this also creates the
admin account and stores your API token:

```bash
hop3 init --ssh root@your-server.com
```

If you've used `kubectl` contexts to switch between clusters, this will feel familiar — Hop3 has the same notion of named server contexts, and `hop3 server use` is the equivalent of `kubectl config use-context`.

## Step 2: Export Your Kubernetes Configuration

Your manifests (or your Helm chart's rendered output) are the starting point. The two things you'll actually carry over are the environment from your `ConfigMap`s and the values from your `Secret`s.

Dump the non-sensitive config as plain key-values:

```bash
kubectl get configmap web-config -o jsonpath='{.data}' > config.json
```

Secrets are base64-encoded in the API, so decode them — you'll re-set the values in Hop3, not the encoded blobs:

```bash
kubectl get secret web-secrets -o go-template='
{{- range $k, $v := .data}}{{$k}}={{$v | base64decode}}{{"\n"}}{{end}}'
```

Then plan to drop the entries Hop3 sets for you:

- `DATABASE_URL` (will be set by the Hop3 Postgres addon)
- `REDIS_URL` (will be set by the Hop3 Redis addon)
- `PORT` (auto-set by Hop3)
- Anything injected by the downward API (`POD_NAME`, `POD_NAMESPACE`, `NODE_NAME`, …) — these have no meaning off a cluster

## Step 3: Add hop3.toml

Here's where the concept mapping gets concrete. A representative Kubernetes setup for one web app — a `Deployment`, a `Service`, an `Ingress`, a `ConfigMap`, a `Secret`, and a `PersistentVolumeClaim` — is several files. Condensed, it looks roughly like this:

```yaml
# deployment.yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: web
spec:
  replicas: 2
  template:
    spec:
      containers:
        - name: web
          image: registry.example.com/web:1.4.2
          ports:
            - containerPort: 8080
          envFrom:
            - configMapRef: { name: web-config }
            - secretRef: { name: web-secrets }
          volumeMounts:
            - name: uploads
              mountPath: /app/uploads
          readinessProbe:
            httpGet: { path: /health/, port: 8080 }
      volumes:
        - name: uploads
          persistentVolumeClaim: { claimName: uploads-pvc }
---
# service.yaml + ingress.yaml route :80 -> :8080 for web.example.com
```

The same app as a single `hop3.toml`:

```toml
[metadata]
id = "web"

[build]
builder = "docker"

[env]
# From your ConfigMap and decoded Secret — re-set the values here,
# or out of band via `hop3 env set` so they never touch the repo
SECRET_KEY = "your-secret-key"
DJANGO_SETTINGS_MODULE = "myapp.settings.production"

[run]
before-run = ["python manage.py migrate"]

[[volumes]]
name = "uploads"
target = "data/uploads"

[healthcheck]
path = "/health/"

[domains]
list = ["web.example.com"]
```

Each Kubernetes object lands on a Hop3 one, and the file count drops from six to one:

- **`Deployment` → the Hop3 app itself.** The unit you deploy. `metadata.name` becomes `[metadata].id`.
- **`Service` + `Ingress` simply disappear.** You don't write them. Hop3 configures nginx automatically: it assigns a dynamic `$PORT`, routes by hostname to your app, and terminates TLS at the proxy. The `containerPort: 8080` becomes "make your app read `$PORT`" — drop the hardcoded port. No Ingress controller, no annotations, no `IngressClass`.
- **`ConfigMap` → `[env]`** (and `kubectl set env` → `hop3 env set` for changes after deploy).
- **`Secret` → `[env]` too, but encrypted at rest.** Hop3 stores env values encrypted in its database, so secrets and plain config live in the same place without the base64 ceremony. For database and cache credentials you copy nothing — see Step 4.
- **`PersistentVolumeClaim` + `volumeMounts` → `[[volumes]]`.** Kubernetes' `mountPath` is an absolute path bound to a PVC; Hop3's `target` is a directory inside the app tree (relative, no `..`) that survives redeploys, stored under the app's data root outside the source tree that gets replaced each deploy.
- **`readinessProbe` → `[healthcheck]`.** Same idea, one path.
- **`replicas: 2` → manual scaling.** There's no HPA. You set process counts yourself with `hop3 ps scale` (Step 7), and they run on the one host rather than being scheduled across nodes.
- **The container `image` → `[build] builder = "docker"`.** Hop3 builds from your `Dockerfile`. (See the next section if you'd rather drop the image entirely and let Hop3 build natively.)

## Step 4: Migrate Your Database

If your database ran in the cluster as a `StatefulSet` (or via an operator like CloudNativePG or the Zalando Postgres operator), you're moving it off the cluster and onto a managed Hop3 addon.

### Export from Kubernetes

Dump the database through a port-forward, the ordinary way:

```bash
kubectl port-forward statefulset/postgres 5432:5432 &
pg_dump "postgres://postgres:PASSWORD@localhost:5432/your_app" \
    -Fc -f latest.dump
```

This creates `latest.dump`.

### Import to Hop3

First, create the database addon and attach it to your app:

```bash
hop3 addon create postgres web-db
hop3 addon attach web-db --app web
```

Get the connection details:

```bash
hop3 addon show web-db
```

Import the dump:

```bash
# Copy dump to server
scp latest.dump root@your-server.com:/tmp/

# SSH to server and import
ssh root@your-server.com
sudo -u postgres pg_restore --verbose --no-owner \
    -d web_db /tmp/latest.dump
```

## Step 5: Deploy to Hop3

Add Hop3 as a remote:

```bash
git remote add hop3 hop3@your-server.com:web
```

Deploy:

```bash
git push hop3 main
```

That `git push` is the whole pipeline. There's no image to push to a registry first, no `kubectl apply`, no Helm release to bump — Hop3 builds from the pushed source (or your Dockerfile) and brings the app up.

## Step 6: Point Your Domain

In the cluster, an `Ingress` plus an external load balancer or the ingress controller's IP handled this. On Hop3 you point a record at your one server:

```
web.example.com  A  your-server-ip
```

Once Let's Encrypt is configured on the server, Hop3 requests a certificate for the domain at deploy time. Out of the box, a freshly installed server serves a self-signed certificate until you point it at an ACME provider. (This replaces cert-manager: no `Certificate` resources, no `ClusterIssuer`.)

## Common Migration Issues

### Container Image vs Native Toolchains

Kubernetes always runs a container — you built an image, pushed it to a registry, and referenced it by tag. Hop3 can do the same with `[build] builder = "docker"`, so the simplest migration keeps your Dockerfile unchanged and skips the registry round-trip.

But you often don't need the image at all. Hop3 auto-detects a native toolchain from the files in your repo — Python, Node.js, Go, Ruby, Rust, Java, PHP, Elixir, .NET — and builds without a container. If your Dockerfile was just "install the runtime, copy the code, run the server", you can usually delete it and let Hop3 detect the language:

```toml
[build]
toolchain = "python"
```

For a multi-language build (say, Python plus a Node asset step), use `before-build`:

```toml
[build]
toolchain = "python"
before-build = "npm install && npm run build"
```

Keep `builder = "docker"` when your image does something Hop3's toolchains don't — a system package, a compiled extension with awkward deps, a pinned runtime version. There's also a Nix builder and a static-site builder for the cases in between.

### Workers and Sidecars

A Kubernetes pod often runs more than one container — the main app plus a worker or a sidecar. Hop3 models extra long-running processes as workers in `hop3.toml`:

```toml
[run.workers]
worker = "celery -A myapp worker"
```

This is the equivalent of a second `Deployment` (or a second container in the pod) for a background worker. True infrastructure sidecars — a service-mesh proxy, a logging agent — don't carry over: there's no mesh, and on one host logs and metrics are already local.

### CronJobs

A Kubernetes `CronJob` becomes either a worker (if it's a long-running scheduler you control) or plain system cron on the one box. For a framework scheduler like Celery beat:

```toml
[run.workers]
scheduler = "celery -A myapp beat"
```

For a one-shot periodic task — the closest analogue to a `CronJob` running a single command on a schedule — use system cron:

```bash
ssh root@your-server.com
crontab -e
# Add: 0 * * * * /home/hop3/apps/web/venv/bin/python /home/hop3/apps/web/src/manage.py cleanup
```

### Secrets

Kubernetes `Secret`s are base64-encoded objects (and, by default, only encrypted at rest if you configured EncryptionConfiguration). Hop3's `[env]` stores values encrypted in its database without the base64 dance, so secrets land in `[env]` in `hop3.toml`, or you set them out of band so they never touch the repo:

```bash
hop3 env set --app web SECRET_KEY=… STRIPE_KEY=…
hop3 app restart web
```

Database and cache credentials are the special case: you don't copy them at all. When you attach an addon, Hop3 injects `DATABASE_URL`, `REDIS_URL`, and friends for you, so drop those from your secret list entirely.

### Keeping an External Managed Database

Maybe your cluster talked to a managed Postgres outside it (RDS, Cloud SQL, Neon) that you're not ready to move. You don't have to. Skip the addon and point `[env]` at the existing URL:

```toml
[env]
DATABASE_URL = "postgresql://user:pass@db.example.com:5432/mydb"
```

Hop3 won't manage that database, but your app talks to it exactly as before. You can adopt a Hop3 addon later.

### Postgres Extensions

If your app relies on a Postgres extension (`pg_stat_statements`, `pgcrypto`, …) that your operator or init container used to enable, enable it on the Hop3 addon without SSH or manual `psql`:

```bash
hop3 addon postgres extensions web-db pg_stat_statements
```

Extensions are allow-listed, so only the ones Hop3 ships support for will install.

### Redis and Object Storage

If Redis ran in-cluster, most of it is cache — let it warm up fresh. If you do have data to keep, dump it and load it into the Hop3 addon:

```bash
# Or just start fresh — most Redis data is cache
hop3 addon redis import web-cache --confirm=web-cache < dump.rdb
```

If your app used an in-cluster MinIO (or reached out to S3) for object storage, Hop3 has an S3/MinIO addon — attach it the same way as a database, and Hop3 injects the `S3_*` connection vars.

### Non-HTTP Ports

If a pod exposed a raw TCP/UDP port that wasn't HTTP — a `NodePort` Service for SMTP, RTMP, a game server — that's not the HTTP path. HTTP apps use the dynamic `$PORT` and are proxied by hostname, so they never declare a port. A fixed host port is declared with `[[ports]]`:

```toml
[[ports]]
number = 1935
protocol = "tcp"
name = "rtmp"
```

Hop3 records each fixed port in a host-wide registry and refuses a second app that wants the same one — before it builds — so two apps can't silently fight over it.

### Scaling, and What You Give Up

This is the gap that matters most for Kubernetes users, so it's worth being plain about it. Hop3 has no Horizontal Pod Autoscaler, no Cluster Autoscaler, and no multi-node scheduling. Scaling is manual and it happens on one box: you set the process counts yourself.

```bash
hop3 ps scale web web=3 worker=2
```

That bumps the number of web and worker processes on the server — vertical headroom on a single host, not pods spread across nodes. There is no rolling deploy across replicas (the app restarts on the one host) and no service mesh. If your app needed the HPA to absorb real, spiky, multi-node load, Hop3 is not a substitute — that workload belongs on a cluster. If `replicas: 2` was mostly there for availability theatre on a service that never came close to saturating a node, a single right-sized server with a couple of worker processes will carry it, and you stop paying for the scheduler you weren't using.

## Command Mapping

| Kubernetes Command | Hop3 Command |
|--------------------|--------------|
| `kubectl create` / `kubectl apply` (new app) | `hop3 app create` |
| `kubectl get deployments` | `hop3 app list` |
| `kubectl describe deployment web` | `hop3 app status --app web` |
| `kubectl get configmap` / `get secret` | `hop3 env show --app web` |
| `kubectl set env deployment/web K=V` | `hop3 env set K=V --app web` |
| `kubectl logs -f deployment/web` | `hop3 app logs --app web` |
| `kubectl get pods` | `hop3 ps --app web` |
| `kubectl scale --replicas=N` / HPA | `hop3 ps scale --app web web=N` |
| `kubectl rollout restart deployment/web` | `hop3 app restart --app web` |
| `kubectl exec -it … -- bash` | `hop3 app run --app web` |
| StatefulSet / DB operator | `hop3 addon create postgres <name>` |
| `kubectl apply -f pvc.yaml` | `[[volumes]]` in `hop3.toml` |
| `Ingress` + cert-manager | `hop3 domain add <host> --app web` |
| `kubectl config use-context` | `hop3 server use <name>` |

## Cost and Lock-In

Kubernetes costs more than the nodes. A managed cluster bills you for the control plane (EKS and GKE and AKS each charge per cluster-hour on top of the worker nodes), and then there's the part that doesn't show up on the invoice: the load balancer per Ingress, the persistent volumes, the cross-AZ traffic, and the engineering hours spent on chart upgrades, controller CVEs, and etcd you hope you never have to restore. Self-hosted k3s removes the control-plane line item but keeps the operational one — you are now the person who patches the cluster. Hop3's bill is a VPS, and adding an app or a worker process doesn't change it.

| | Kubernetes | Hop3 (self-hosted) |
|-|------------|-------------------|
| Control plane | per-cluster (managed) or self-run (k3s) | none |
| Compute | per-node fleet | fixed VPS |
| Load balancer | per Ingress / Service | included (nginx on the VPS) |
| Database | StatefulSet + PV, or managed DB | included on the VPS |
| **Small app** | cluster + node + LB + PV | ~$10/month (VPS) |
| **Medium app** | grows with nodes and LBs | ~$30/month (VPS) |

The lock-in angle is the quieter win. On Kubernetes your app is shaped around the cluster: manifests, Helm charts, CRDs, controller-specific annotations, and a deploy pipeline that knows how to render and apply all of it. Some of that is portable across clusters; the operator-specific and cloud-specific parts are not. On Hop3 your app is a Dockerfile (or a plain native build), a Postgres you can `pg_dump`, and one config file in your repo — nothing that only one orchestrator can run. If you ever outgrow Hop3 and go back to a cluster, you go back with a standard, containerizable app, not one welded to a particular control plane. The trade-off is the obvious one: you manage the server, but you control everything on it — and there's a lot less of it to manage.

## Rollback Plan

Keep your cluster running during migration — a `Deployment` you don't touch keeps serving:

1. Deploy to Hop3 with a test domain (or a subdomain of your own)
2. Verify everything works against real data
3. Switch DNS to point at your Hop3 server
4. Keep the cluster workload running for 1–2 weeks
5. `kubectl delete -f` (or `helm uninstall`) the app, and tear down the cluster, once you're confident

Because DNS is the only switch, rollback is just pointing the record back at the Ingress — no data has to move twice.

## Getting Help

- [Hop3 Documentation](https://hop3.cloud)
- [GitHub Issues](https://github.com/abilian/hop3/issues)
- [Troubleshooting Guide](/guides/troubleshooting/)

---

*Coming from a different platform? The concepts are similar. Check the [Getting Started guide](/get-started/) for a fresh start.*
