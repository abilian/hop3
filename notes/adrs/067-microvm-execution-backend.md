# ADR 067: Micro-VM Execution Backend

- **Status**: Draft
- **Type**: Architecture
- **Created**: 2026-10-27
- **Revised**: 2026-10-28 (per-app users ship in Hop3 0.9), 2026-10-29 (hardened hosts)
- **Related-ADRs**: [009](./009-nix-runtime.md) (the Nix runtime, whose isolation between workloads this delivers), [023](./023-runtime-stack-replacement.md) (the process manager under which VMs would run), [041](./041-privileged-operations-agent.md) (the privileged helper, which owns the host objects a VM needs), [046](./046-declarative-app-resources.md) (memory and CPU limits), [055](./055-app-runtime-uid-separation.md) (per-app users, the lighter boundary), [063](./063-identity-layer.md) (the sign-in socket a guest reaches), [065](./065-workload-identity.md) (workload identity: a guest known by the socket the platform made for it), [068](./068-guest-networking.md) (platform networking: the guest's tap and rules), [069](./069-worker-servers.md) (worker servers and placement, which reads the capability of §6), [071](./071-sandboxed-builds.md) (sandboxed builds, which reuse this guest)

## Context

[ADR 009](./009-nix-runtime.md) deferred a Nix runtime with isolation between workloads, which Hop3's NGI0 plan announced alongside lightweight VMs. Per-app Unix users ([ADR 055](./055-app-runtime-uid-separation.md)) are the lighter step; this ADR is the strongest one.

Until Hop3 0.9, all native and Nix apps ran as the same `hop3` user: code execution in one app was code execution as the platform, which read the other apps' files, environment and addon credentials, and reached the privileged helper with the right UID. From 0.9, each app runs under its own Unix user (ADR 055). Per-app users separate files, environments and credentials, but share one kernel and the host's network. A kernel flaw or a misconfigured permission still crosses them.

A micro-VM gives an app a separate kernel and memory, and only the files the platform shares with it. A self-hosting platform needs three things from it: the app keeps the usual build and recipe, the operator learns nothing about monitors, and the app keeps the contract of a native app (a port, an environment, a health check, logs).

Running an app in a VM breaks what one host and one kernel make true. Inside the guest, `127.0.0.1` is the guest itself. A Unix socket on the host does not cross the boundary. The guest's `/etc`, `/var` and `/tmp` are no longer the host's. The app's home comes from the guest's `passwd`. The process the platform starts may be PID 1. Each of these is a platform concern.

Some hosts cannot run a VM. Most rented VPS expose no `/dev/kvm`; dedicated servers do.

## Decision

We propose the following.

### 1. A deployer chosen per app

The micro-VM backend is a deployer alongside uWSGI, static and Docker. An app runs in a VM when the recipe asks for it (`[deploy] deployer = "microvm"`) or when the platform's default says so and the app does not lower it. An app may raise the platform's default; it may not lower a default the operator set. A host that cannot run VMs refuses such an app with a diagnosis naming what it lacks, and does not fall back to running it natively. On a platform with worker servers, placement (ADR 069) puts a VM app's workers only on servers that report hardware virtualisation (§6); when none does, the deploy is refused with the same diagnosis.

### 2. Cloud Hypervisor behind a monitor interface

The target monitor is Cloud Hypervisor: it supports virtio-fs, vsock and a balloon with free page reporting, and has a lower idle overhead than QEMU. QEMU's `microvm` machine is the fallback, kept until Cloud Hypervisor has run every golden app on every supported distribution; both come from nixpkgs (§6), and open question 3 decides whether QEMU is kept. Firecracker has no virtio-fs, so sharing the store would need images; libkrun is kept under review. The launcher should talk to the monitor through one small interface (start, stop, sockets), so the choice stays reversible.

### 3. No image

One guest kernel and one small initrd, built with Nix, serve all apps on the server. The guest boots the app's existing build artifact:

- The Nix store over virtio-fs, **read-only on the host side** (virtiofsd 1.11 or later; an older one is refused, since a guest's root could remount a writable share).
- For native builds, the host's `/usr` read-only, and an `/etc` assembled only from an allow-list of runtime configuration (PHP and Java runtime configuration, for example). Every worker server runs the primary's distribution release (ADR 069), so a native release built on the primary finds the same `/usr` on whichever server runs it.
- The app's directory and data at the same paths as on the host, so paths in the app's configuration stay valid.
- A writable `/var` and `/tmp` per app, in the app's directory, shared by all the app's guests.
- A `passwd` that gives the app's user the app's own home.

### 4. The init and the guest agent

The init stays PID 1. It mounts the guest's devices, starts the app as an unprivileged user, reaps orphans, and powers the guest off when the app exits, so the supervisor on the host sees the exit and restarts it.

A guest agent listens on vsock. It runs, inside the app's running guest and with the step's own environment: post-deploy steps that talk to the running app, workers besides `web`, `hop3 run`, and `hop3 app shell` on a pty. One guest serves all the app's workers on a server, so file locks and watches hold among them. A step that does not need the running app runs in a one-shot guest with the same mounts. The environment travels on the connection and stays off any command line in the guest.

### 5. The same contract as a native app

The environment is built as for a native worker. The app binds its `$PORT`; the health check, the proxy and the logs work as for a native app. A guest reaches the addons it declared over the tap, by the rules of ADR 068 §2; platform services (the sign-in socket, the guest agent) cross over vsock, where the host knows the caller by its socket (ADR 065). Secrets stay off the monitor's and virtiofsd's command lines: the guest's environment is a file only the launcher can read, one per launch.

The launcher runs under the app's supervisor. It owns the monitor and the virtiofsd processes, which die with it even when it is killed; when the supervisor restarts it, it starts a fresh guest. Destroying the app leaves no monitor, virtiofsd, socket, runtime directory or host object (ADR 068).

### 6. Host support

- **The installer** takes the monitor, virtiofsd and the guest kernel and initrd from the pinned nixpkgs, the same on every supported distribution, since none packages Cloud Hypervisor and several lack a virtiofsd that shares read-only. VM support therefore requires Nix on the host. The monitor and virtiofsd run as the app's user (§5), for the run-time guest and for the build guest of ADR 071, so the privileged helper, which creates that user (ADR 055), puts it in the group that owns `/dev/kvm`. The shares need no permission the app's user lacks: the store and `/usr` are world-readable and the app's directory is its own.
- **Hardened hosts.** The installer ships its own udev rule for `/dev/kvm`, since no distribution QEMU is installed to provide one. On a host with SELinux enforcing, the monitor needs the labelling of the store that Nix-built apps already need, plus access to the `kvm` device and to vsock sockets, checked per release. Where unprivileged user namespaces are disabled (Ubuntu's AppArmor restriction, hardened kernels), virtiofsd runs as the app's user with the namespace sandbox off, which leaves it that user's rights and no more, or in chroot mode started by the privileged helper; the capability check reports which. Each case is checked on each supported distribution, per release.
- **Capability check.** Each server reports whether it can run VMs (`/dev/kvm`, vsock, the monitor, virtiofsd's version) in its status, which placement reads, and refuses a VM app with a diagnosis naming the missing piece.
- **Memory.** A guest's size defaults generously; a declared `[limits].memory` sets it exactly. The host's cgroup limit for the app is that size plus the monitor's measured overhead. A balloon with free page reporting returns what a guest frees.
- **Figures** should be published per release on the golden apps: boot time, memory per idle VM and per app against native, and apps per server.

### 7. Fixes in the platform

A guest that breaks a single-host assumption is fixed in the platform for all apps (the addon address the guest sees, a relay for a host socket, the guest's `/var`). Recipes stay free of workarounds for it.

## Acceptance

- Each golden app not shipped as an image passes its check in a VM, on a fresh server, with its recipe unchanged except for the deployer choice; an exception is published with the reason.
- A server without `/dev/kvm` refuses a VM app with a diagnosis; an app that asked for a VM does not end up running natively.
- On a platform whose worker servers differ in hardware virtualisation, a VM app's workers run only on those that have it.
- Killing the monitor or the launcher brings the app back; destroying it leaves no process, socket, file or host object.
- No secret appears in any host process's command line, checked by test.
- A writable store share, or a virtiofsd older than 1.11, is refused.
- `hop3 run` and `hop3 app shell` execute in the guest's kernel, as the app's user.

## Consequences

### Positive

- Code execution in one app no longer reaches the others or the platform.
- No image format, registry or rebuild: the recipe stays the same.
- Running apps under a stricter environment exposes coexistence defects that native deployments share. The platform fixes them for all apps.

### Negative

- Memory per app rises by the monitor's and guest kernel's overhead, so fewer apps fit on a server.
- VM support depends on Nix on the host, for the monitor and virtiofsd.
- VPS without hardware virtualisation get no benefit. A primary on such a VPS also builds unsandboxed (ADR 071, open question 5).
- Steps, workers and shells take a path through the guest agent that native apps do not.

## Alternatives considered

- **Containers (Docker, Podman)** buy familiar tooling. They cost images, a registry and a shared kernel. Hop3 keeps them as a separate backend for apps that ship as images.
- **Kernel-sharing sandboxes** (bubblewrap, systemd-nspawn, gVisor) are cheaper in memory. They share the host's kernel, or reimplement it. They remain candidates for a lighter level beside per-app users.
- **Kata Containers** give VM isolation with the whole container stack attached. A need for OCI compatibility at the VM level would change this choice.
- **One image per app** gives a simpler guest. It costs a build step and storage per app, and diverges from the native artifact.

## Open questions

1. **Platform default.** Whether new platforms whose servers can run VMs default to them, or keep native apps until the operator opts in. Decided by the measurements of memory per app (§6).
2. **Window resize** for `hop3 app shell` in a guest. Decided when the guest agent's shell protocol is designed.
3. **Monitor parity.** Whether QEMU stays supported once Cloud Hypervisor covers every host Hop3 installs on, and whether QEMU's vsock, addressed by a host-wide number, gives the same caller guarantee as a socket per VM (ADR 065). Decided once Cloud Hypervisor has run every golden app on every supported distribution.
4. **Nested virtualisation.** Whether a host whose `/dev/kvm` is nested qualifies, and at what measured cost; we measure it before relying on it. Decided by the measurements of §6.
