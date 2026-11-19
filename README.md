# The wand maker's digital apprentice

![Welcome the wand maker's digital apprentice](docs/img/welcome.jpg)

A wand maker can't find an apprentice, so he hires an AI one. It's quick, it's polite, and it
never sleeps. Then four questions keep the old man awake. Can we limit what it does? Can we see
what it did? Can we trust it enough to ship it? And does it survive the day the whole school
shows up?

This repository is the demo behind our talk "Operate your agents – safely!". It's a small shop
with one AI employee, built on Red Hat
OpenShift AI, and a slide deck that drives the real thing while you talk.

## Four questions, four chapters

Think of a new hire on their first day. You don't hand them the master key. You give them a desk
and a few tools, and somebody looks over their shoulder for a while. We do the same with the
agent, one chapter per question:

| Chapter | The question | What answers it |
|---|---|---|
| Contain | Can we limit what it does? | The agent (OpenClaw) runs in an OpenShell sandbox. It reaches the shop's tools through an MCP gateway and nothing else, and the cabinet with the restricted stock stays locked until the wand maker says yes. |
| See | Can we see what it did? | Every customer visit is a trace in MLflow. Every call the sandbox refused is in OpenShell's audit log. |
| Trust | Can we ship it? | NeMo Guardrails sit in the model path, in and out. A red-team campaign decides whether a rails release may ship: release 1.5 fails, release 1.5.1 passes. |
| Scale | Does it survive the rush? | The audience scans a QR code and talks to three apprentices at once, while a model gateway spreads the calls over several model endpoints. |

## What it runs on

Where does all of this come from? From one place. Every piece below is part of Red Hat OpenShift
AI today or on its way into it, and that's the message of the talk: the platform you already
serve models on is the one you operate agents on.

| Chapter | What we used |
|---|---|
| Contain | OpenClaw as the agent, NVIDIA OpenShell as the sandbox around it (network policy, credentials kept outside the agent), the Agent Sandbox operator, and the MCP gateway in front of the shop's tools |
| See | MLflow for the traces, fed over OpenTelemetry by OpenClaw's own instrumentation, plus OpenShell's audit log for every allow and deny |
| Trust | NeMo Guardrails through the `NemoGuardrails` resource, with the rules in a ConfigMap. The red-team runs land in MLflow; in the product that job belongs to EvalHub with Garak |
| Scale | A model gateway in front of several OpenAI-compatible endpoints, the job Models-as-a-Service does in the product, and three sandboxed apprentices side by side |

We left the maturity labels out on purpose. Which piece is a preview and which is generally
available changes with every release, so check the current OpenShift AI release notes before you
plan with any of them.

## How it fits together

![The architecture: the apprentice in its sandbox, the two gateways, guardrails, and the shop's tools](docs/img/architecture.jpg)

Read the picture from left to right. A customer types into the shop front. The line lands with
the digital apprentice, who lives inside the dashed box, and that box is the point: whatever the
agent wants from the world has to leave through one of two doors.

The upper door leads to the model. Calls go through the model gateway, pass the guardrails on the
way in and on the way out, and only then reach the oracle (you've heard of it as an LLM). The
lower door leads to the tools. The tool gateway hands out the wand catalogue, the notebooks and
the ledger. And the locked cabinet? The apprentice can ask for it, but a human signs first.

Below the box sit the two things that let you sleep. The day's scroll keeps what happened, as
MLflow traces and as the sandbox's audit log. The release gate keeps a new version out of the shop
until the red team has had a go at it.

One honest note on the picture: it shows the target. The red-team campaign in this repository is
our own runner, not Garak, and the models run at endpoints you bring, not on GPUs in the cluster.

## Look at the talk right now

The deck in `deck/` is a plain web page. Without a cluster it plays every demo from a script, so
you can click through the whole talk on a laptop:

```bash
git clone https://github.com/maxisses/thewandmaker-agentops.git
```

```bash
python3 -m http.server 8765 --directory thewandmaker-agentops/deck
```

Open http://127.0.0.1:8765, press F for fullscreen and N for the speaker notes.

## Build the live version

For the live demo, bring an existing OpenShift 4.22 cluster with cluster-admin access and an
OpenAI-compatible model endpoint. ROSA, AWS and a bastion are optional. The OpenShell CLI runs
on your own machine (Linux or macOS).

Point your agent at [AGENTS.md](AGENTS.md). It opens with the prerequisites as a checklist, and
`make preflight` checks them without changing anything:

```bash
cp .env.example .env
```

Fill in the model settings in `.env`, then authenticate to your cluster:

```bash
oc login <your-api-url>       # use your cluster's interactive login
# export KUBECONFIG=/path/to/config  # optional; otherwise oc uses ~/.kube/config
make openshell-cli          # install pinned OpenShell 0.0.116
export PATH="$HOME/.local/bin:$PATH"
make preflight
make up-platform
```

Install `oc`, `helm`, Python 3.9+, Bash, Make, OpenSSL, Git, curl and coreutils (`timeout`, or
`gtimeout` on macOS). The cluster needs a default storage class, a managed internal image
registry, sufficient worker capacity, outbound image/model access, and the operator channels
listed in [AGENTS.md](AGENTS.md). The installer does not create users or resize your cluster.
`make up-platform` recreates the apprentice sandboxes, clearing their audit logs.

All deployment and rehearsal commands use your current `oc` context. Existing ROSA users who
keep credentials in the old location must explicitly export `KUBECONFIG="$PWD/local/kubeconfig"`.
Optional ROSA provisioning remains available with `make up` and `make up-access`; the old saved
admin login is `make rosa-cluster-login`. Set both bastion variables only for remote CLI execution.
See [docs/existing-cluster.md](docs/existing-cluster.md) for setup and verification.

Once the preflight is clean, `make up-platform` installs everything in about ten minutes. The
deck then runs on the cluster too, behind a password you set in `.env`, and its first slide has
the buttons to prepare and reset a run.

## Where things are

| Path | What it is |
|---|---|
| [AGENTS.md](AGENTS.md) | Prerequisites, build order, traps. Start here. |
| `gitops/` | The platform, one folder per piece, numbered in install order |
| `apps/shop/` | The shop: tools, chat, desk, model gateway, the presenter's backstage page |
| `deck/` | The slides, the intro film and the demos in one page |
| `scripts/` | Preflight, cluster login, the local/optional remote CLI runner, the night run, the red-team campaign |
| `infra/` | Terraform for a ROSA cluster, if you don't have one |
| `film/` | How the intro film was cut |
| [REHEARSAL.md](REHEARSAL.md) | A test run of the talk, and back to zero |
| [docs/walkthrough.md](docs/walkthrough.md) | What the cluster does on every slide |
| [docs/build-journal.md](docs/build-journal.md) | Our diary: what we built, what bit us, the numbers |
| [STORYLINE.md](STORYLINE.md), [RESEARCH.md](RESEARCH.md) | The story, and what the platform really offers behind it |

## Good to know

We built this for one talk on one cluster. Nobody has rebuilt it from a clean clone yet, and two
of the operators come from preview channels. Treat it as a worked example, and expect to fix a
thing or two on the way.

The live demo taught us something as well. With about 40 phones in the room, the audience got
answers in Russian and Chinese past the "answer in English" rail, and the guarded name once
slipped out with a Cyrillic letter in it. Both holes are closed now, and the story is in the
[build journal](docs/build-journal.md). That's what a red team is for.

The pictures, the film and its sounds were generated with Higgsfield.

## Licence

There's no licence file yet. Until one is added, the usual rule applies: you may read the code,
and everything else needs a word with the authors.
