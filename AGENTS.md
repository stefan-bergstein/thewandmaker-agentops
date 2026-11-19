# For the agent that builds this

You've been asked to stand up the demo behind the talk "Operate your agents – safely!": an AI shop
assistant (OpenClaw) locked into an OpenShell sandbox on OpenShift, with a tool gateway, tracing
in MLflow, NeMo Guardrails and a slide deck that drives all of it live.

Don't start with `make up-platform`. Start here:

```bash
cp .env.example .env      # your human fills it in; never print or commit it
make preflight            # read-only; lists what is missing
```

`make preflight` changes nothing, on your machine, the cluster or the bastion. Run it until it
says "Nothing required is missing", and ask your human for whatever it lists. Most of the list
below is something only a person can bring.

## What you have to bring

### 1. An OpenShift cluster

- [ ] **OpenShift 4.22.** Built and tested on 4.22.21, ROSA with hosted control planes, AWS
      eu-central-1. The OpenShell sandbox's security context constraint needs image volumes, so
      older versions are a risk we haven't tried.
- [ ] **cluster-admin.** The build creates SCCs, cluster roles, operator subscriptions and
      namespaces (`ollivanders`, `openshell`, `olli-build`, plus the operators' own).
- [ ] **About 30 vCPU and 120 GiB of worker capacity.** Ours: 2 × m6a.xlarge plus 3 × m6a.2xlarge.
      No GPU. The models run somewhere else; the "model pool on our own GPUs" in the deck is an
      illustration.
- [ ] **A default storage class.** MLflow claims 10 Gi without naming one.
- [ ] **The internal image registry, managed.** The shop, the deck and the sandbox image are built
      on the cluster with BuildConfigs. You don't need podman or docker on your machine.
- [ ] **An ingress certificate that browsers accept.** The audience scans a QR code with their
      phones, and the deck frames pages from the cluster. ROSA brings one.
- [ ] **Outbound access from the cluster** to `registry.access.redhat.com`, `quay.io`, `ghcr.io`
      (OpenShell's helm chart and the OpenTelemetry collector), GitHub releases (the OpenShell CLI,
      at image build time), PyPI, and your model endpoints. The standard Red Hat pull secret is
      enough; none of our images needs a login of its own.
- [ ] **The `redhat-operators` catalog** with these packages and channels. Two are preview channels:

| Package | Channel | What for |
|---|---|---|
| `rhods-operator` | `stable-3.5` | Red Hat OpenShift AI 3.5 (we ran 3.5.3): dashboard, KServe, AI gateway, MLflow, TrustyAI with NeMo Guardrails, MCP lifecycle |
| `openshift-cert-manager-operator` | `stable-v1` | needed by OpenShift AI |
| `leader-worker-set` | `stable-v1.0` | needed by OpenShift AI |
| `mcp-gateway` | `preview` | the tool gateway in front of the shop's tools |
| `agent-sandbox-operator` | `preview-0.9` | Red Hat build of Agent Sandbox, under OpenShell |

OpenShell itself (0.0.116) comes as a helm chart from `ghcr.io/nvidia/openshell`, with the Open
Data Hub images set in `gitops/02-openshell/values.yaml`.

No cluster yet? `make up` builds a ROSA HCP cluster with Terraform (`infra/`), in about
20 minutes. That needs an AWS account with ROSA enabled and linked to a Red Hat account, which
costs money and takes three manual steps: see [docs/manual-steps.md](docs/manual-steps.md). Copy
`infra/context.example.json` to `infra/context.json` first and put the AWS account ID in;
`scripts/tf.py` refuses to run against any other account.

### 2. An OpenShell CLI on your machine

ROSA, AWS and a bastion are optional. Authenticate with `oc login` using your cluster's identity
provider. All deployment and rehearsal commands honor `KUBECONFIG`; without it, they use the
standard `~/.kube/config`. Install the pinned CLI with `make openshell-cli`, add
`$HOME/.local/bin` to `PATH`, then run `make preflight` and `make up-platform`.
Linux and macOS need coreutils (`timeout` or `gtimeout`).

For optional remote execution, set both `BASTION_HOST` and `BASTION_USER` in `.env`. The remote
host needs authenticated `oc`, Bash, OpenSSL, coreutils and OpenShell (`make bastion-cli`).
Without these settings sandbox scripts run locally. `up-access` remains a separate ROSA-only
helper; the platform build never creates cluster users or machine pools.

### 3. Models

The apprentice needs an OpenAI-compatible chat completions endpoint that can call tools and takes
a 44,000-token system prompt (that's OpenClaw's own).

- [ ] **Required: `model`, `modelendpoint`, `modelkey`.** We used Red Hat's internal
      Models-as-a-Service; outside Red Hat, put any OpenAI-compatible endpoint there. The
      guardrails call it directly, and OpenShell holds its key so the sandbox never sees it.
- [ ] **Optional: `OPENROUTER_API_KEY`.** Paid. On `deepseek/deepseek-v4.1-flash` we measured 60 model calls for
      0.27 US cents, so a full rehearsal stays far below one dollar.
- [ ] **Optional: `REDHATTMM_BASE_URL`, `REDHATTMM_MODEL`, `REDHATTMM_API_KEY`.** A second spare
      endpoint. Set all three or none.

Who answers first? The model gateway (`apps/shop/shop/modelgw.py`) is configured in
`gitops/20-shop/install.sh`. As shipped (`ORACLE_MODE: backup-first`) the order is OpenRouter, then
the `REDHATTMM` endpoint, then the main model. Without an OpenRouter key the main model answers
everything. `make oracle` shows who answered and what it cost. The model name and the provider
pin for OpenRouter (`BACKUP_MODEL`, `BACKUP_REQUEST`) are in the same file; change them there if
that model is gone by the time you read this.

A free or shared endpoint will throttle you. One customer turn is several model calls of 10,000
tokens or more, and the night run sends 40 visits.

### 4. On your machine

| Tool | Needed for | We used |
|---|---|---|
| `oc` | everything | 4.21.17 |
| `helm` | `make up-openshell` | 4.2 |
| `python3` | all scripts, standard library only | 3.11 |
| `bash`, `make`, `openssl`, `curl`, coreutils | the build (`timeout` / `gtimeout`) | Linux or macOS |
| `ssh`, `scp` | optional bastion only | any |
| `git` | `make vendor` | any |
| `terraform`, `aws`, `rosa` | only `make up` | Terraform 1.16, AWS CLI 2 |
| `node`, Chrome, `puppeteer-core` | only `make captures` | Node 26 |
| `ffmpeg`, Pillow | only `make film` | ffmpeg 8 |

The capture tool assumes Chrome on macOS; deployment scripts run on Linux or macOS.
`make shell-ui` runs in the current interactive terminal.

### 5. In `.env`

`.env.example` lists every name with one line on what it is. `make preflight` checks them by name.

## Build order

`make up-platform` runs everything below in this order. On a fresh cluster it took us about
10 minutes; a second run on the finished cluster took 5 min 22 s. Every step waits for itself
(`scripts/wait-for.sh`), so a slow operator catalog makes it longer, not broken.

**Careful on a cluster that already holds a rehearsal:** `up-apprentice`, `up-pool` and therefore
`up-platform` delete and recreate the sandboxes. That empties OpenShell's audit log, which is
what demo 2 shows. Everything else is safe to run again.

| # | Target | What it does | Took us | Check |
|---|---|---|---|---|
| optional | `up-access` (separate from `up-platform`) | ROSA only: cluster-admin, `local/kubeconfig`, `oc` on the bastion, machine pool `olli` (3 × m6a.2xlarge) | 3 min 44 s | `make preflight` |
| 2 | `up-agent-sandbox` | Agent Sandbox operator | with 6: about 1 min | CRD `sandboxes.agents.x-k8s.io` |
| 3 | `up-openshell` | OpenShell gateway, narrow SCC, passthrough route | with 4, 5: 2 min 20 s | `oc get pods -n openshell` |
| 4 | `cli-connect` | Connect the installed local CLI (or optional bastion CLI), mTLS to the gateway | | `openshell status` |
| 5 | `up-openclaw-image` | builds the sandbox image in `olli-build` | | `oc get istag -n olli-build` |
| 6 | `up-operators` | OpenShift AI, cert-manager, LeaderWorkerSet, MCP gateway | | CSVs `Succeeded` |
| 7 | `up-openshift-ai` | the DataScienceCluster | 2 min 3 s | `oc get datasciencecluster` is `Ready` |
| 8 | `up-mlflow` | MLflow tracking server | 1 min 22 s | `oc get mlflow mlflow` is `Available` |
| 9 | `up-shop` | shop image, tools, tool gateway, model gateway, shop front; reads `.env` | 1 min 31 s | prints the shop's URL; `make oracle` |
| 10 | `up-traces` | MLflow experiment, OpenTelemetry collector | with 11, 12: 1 min 23 s | `oc get deploy otel-collector -n ollivanders` |
| 11 | `up-guardrails` | NeMo Guardrails with rails releases 1.5 and 1.5.1 | | `oc get deploy rails -n ollivanders` |
| 12 | `up-maas` | the main model as OpenShell provider behind `inference.local` | | |
| 13 | `up-apprentice` | **recreates** sandbox `apprentice` with policy, config, persona | with 14: 2 min 32 s | `python3 scripts/shop-say.py` gets an answer |
| 14 | `up-pool` | **recreates** `apprentice-2` and `apprentice-3` for the audience's phones | | |
| 15 | `up-deck` | the deck as a pod behind an HTTPS route | not timed | prints the deck's URL |

The Makefile and helpers use the current `oc` context. To use an old project kubeconfig,
explicitly export `KUBECONFIG="$PWD/local/kubeconfig"` before running commands.

After the build, once:

```bash
make campaign     # red-team runs against rails 1.5 and 1.5.1, 3 to 10 minutes each; the deck replays them
make links        # every address of the demo; SECRETS=1 adds the desk key and the admin password
make prepare CHECK=1   # looks at everything, changes nothing
```

`make claw-test` is the quickest proof that containment works: one turn in a throwaway sandbox,
and a `curl https://github.com` from inside it that gets no connection.

## Getting the deck live

The deck is a static page in `deck/`. It has two modes.

- **Scripted.** `python3 -m http.server 8765 --directory deck`, open http://127.0.0.1:8765. No
  cluster needed. This is also what the hosted deck shows to anyone without the key.
- **Live.** `make deck-live` writes `deck/js/config.local.js` with the shop's address and the desk
  key (git ignores it). `make deck-mock` removes it again.
- **Hosted.** `make up-deck` serves the deck from the cluster. The live version opens with the
  link `make links SECRETS=1` prints, or with the password from `DECK_PASSWORD` in `.env`. Slide 1
  is the presenter's guide, with buttons that prepare and reset a run from inside the cluster.

Three slides show screenshots of real product pages. They're baked into `deck/assets/img/captures/`
and show the author's cluster until you run `make captures` (a Chrome window opens and a person
logs in to the OpenShift console) and `make up-deck` again.

[REHEARSAL.md](REHEARSAL.md) is the test run, [docs/walkthrough.md](docs/walkthrough.md) explains
what the cluster does on every slide.

## Traps we already fell into

The long version of each is in [docs/build-journal.md](docs/build-journal.md).

1. **Cluster authentication expires.** Renew it with `oc login` or `make cluster-login`.
   The optional saved ROSA admin flow is `make rosa-cluster-login`.
2. **Don't grant `privileged`.** The upstream guide does; we use the SCC
   `openshell-sandbox-minimum-required` in `gitops/02-openshell/00-namespace-scc.yaml`. If sandbox
   pods are rejected on your version, `OPENSHELL_SCC=privileged make up-openshell` is the fallback.
3. **The upstream OpenClaw sandbox image lacks `ip` and `nsenter`.** That's why we rebuild it
   (`gitops/03-openclaw-image`). Without them the supervisor dies with "Network namespace creation
   failed".
4. **A BuildConfig's ConfigChange trigger fires only once.** After changing `apps/shop`, run
   `make up-shop`; after changing `deck/`, `make up-deck`.
5. **OpenClaw's context window.** The config says 131,072 tokens. With 32k every turn fails with
   "insufficient output budget".
6. **256 conversations and the apprentice goes quiet.** OpenClaw keeps one MCP connection per
   conversation. `mcp.sessionIdleTtlMs` in `gitops/04-openclaw/openclaw.json` closes idle ones;
   the Prepare button also restarts the OpenClaw gateways before a run.
7. **Rate limits look like a broken demo.** A throttled model shows up as slow turns and "lost for
   words". Look at `make oracle` before you debug anything else.
8. **Changing running apprentices without losing the audit log:** `make up-tune` (OpenClaw
   settings), `make up-persona` (persona files), `make up-model-name`, `make up-fd-limit` (after a
   sandbox restarted). Reach for these before `up-apprentice`.
9. **`make night` adds to a count.** It plays 40 visits; run it once per rehearsal, or use the
   Prepare button, which resets afterwards.
10. **MLflow shows everything unredacted.** The guardrails keep one name off the stage; a trace in
    MLflow's own page doesn't.

## What belongs to the author's environment

- `docs/build-journal.md`, `docs/HANDOVER.md` and `docs/walkthrough.md` are a diary. They name the
  author's cluster, bastion and dates. Those hosts are a time-limited lab and are gone or will be.
- The screenshots in `deck/assets/img/captures/` show the author's cluster.
- The stored campaign and night runs live in the author's MLflow. You'll make your own.
- `infra/context.json` and everything in `local/` are per machine and ignored by git.
- Namespaces and sandbox names are the same on every cluster by design: `ollivanders`,
  `openshell`, `olli-build`, `apprentice`, `apprentice-2`, `apprentice-3`.
- The raw film shots (`film/generated/`) aren't in the repository, so `make film` can't re-cut the
  intro. The finished film is `deck/assets/video/intro.mp4`.

Nobody has built this on a second cluster from a clean clone yet. If a step fails that this file
says should work, the file is wrong: fix it in the same change.

## Rules for working in this repository

- Never print, log or commit a value from `.env` or `local/`. The scripts read `.env` as data and
  pass keys over stdin; keep it that way.
- The desk key and the cluster-admin password only appear with `make links SECRETS=1`. Don't run
  that into a transcript.
- On stage the names are white-labelled: "the digital apprentice", "The Wand Shop", "the wand
  maker", "You-Know-Who". The name the guardrails protect is never written in full in the deck or
  on a page the audience sees. Technical names (`ollivanders`, file names, test data) keep the
  originals.
- Files are in English.
