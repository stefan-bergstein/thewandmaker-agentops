# Deploy on an existing OpenShift cluster

Use a cluster-admin context on OpenShift 4.22 with a default storage class, managed internal
registry, trusted ingress certificate and approximately 32 vCPU / 128 GiB worker capacity.
The operator packages and channels are listed in the root AGENTS.md. No cloud account,
ROSA service, GPU or SSH host is required. Earlier OpenShift releases remain unverified.

Install `oc`, `helm`, Python 3.9+, Bash, Make, OpenSSL, Git, curl and coreutils. On macOS,
coreutils provides `gtimeout`; on Linux it provides `timeout`.

```bash
cp .env.example .env
# Fill model, modelendpoint and modelkey privately; optionally set DECK_PASSWORD.
oc login <your-api-url>
# Optional: export KUBECONFIG=/path/to/your/kubeconfig
make openshell-cli
export PATH="$HOME/.local/bin:$PATH"
make preflight
make up-platform
make prepare CHECK=1
make claw-test
make links
```

Preflight is read-only. Resolve its missing requirements before deploying. The platform build
uses the selected cluster, installs operators and creates cluster roles and SCCs. It does not
create a cluster, user or machine pool. Existing OperatorGroups and package subscriptions are
reused. An existing DataScienceCluster keeps its enabled components and options; only the demo
components are enabled. Rerunning it recreates all three apprentices and clears
their sandbox audit logs. Use `make up-tune` or `make up-persona` to preserve those logs.

`make cli-connect` connects the installed OpenShell CLI using the cluster route and client mTLS
certificate. It stores that certificate under `$XDG_CONFIG_HOME/openshell/gateways/olli/mtls`
(default: `~/.config/openshell/gateways/olli/mtls`) with
private permissions. The API, gateway route and model endpoints must be reachable from the
machine running their respective clients. Model keys are passed to subprocesses without
appearing in command arguments. Never share `.env`, kubeconfigs or client certificates.

`make dashboard` opens the Control UI through a local OpenShell forward; `make dashboard-stop`
closes it. `make shell-ui` uses the current interactive terminal on Linux and macOS. Renew
expired authentication with `oc login`. Run `make test` for offline regression checks.

## Optional legacy ROSA path

Terraform provisioning (`make up`) remains in `infra/` and needs the AWS/Red Hat configuration
from `.env.example`. `make up-access` still provisions ROSA admin access and worker capacity
through a bastion. Neither target runs as part of `make up-platform`.

For remote OpenShell execution, explicitly set both `BASTION_HOST` and `BASTION_USER`. Authenticate
`oc` on that host and run `make bastion-cli`. Sandbox commands and dashboard forwarding then use
SSH. Local and remote `oc` must target the same cluster. Existing ROSA project kubeconfigs now
need `export KUBECONFIG="$PWD/local/kubeconfig"`; `make rosa-cluster-login` renews that legacy login.

## Gateway TLS signature errors

The Linux package can install a separate local gateway and certificates. OpenShell 0.0.116's
`gateway add --local` imports that package's certificates by default, replacing the cluster
bundle and causing `invalid peer certificate: BadSignature`. Our connection script disables
that package import and uses the cluster's CA and client certificate with TLS verification enabled.
Run `make cli-connect` to refresh the bundle and registration without recreating cluster resources,
then resume `make up-platform`. An existing gateway name is re-registered with the current route.

## Model readiness checks

The backstage model check runs through the apprentice's authenticated `inference.local` path.
The model gateway expects OpenShell to inject the provider credential; a direct unauthenticated
request from the shop front to `/raw/v1/chat/completions` can return HTTP 401 even when the
configured key works. The readiness check uses the sandbox path so no additional model key is
needed in the shop front. A real authentication failure reports its HTTP status separately from
timeouts and empty model responses.
