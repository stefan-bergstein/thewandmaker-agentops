# Build up and tear down the demo platform. Everything reads credentials from the local .env.
TF = python3 scripts/tf.py
.DEFAULT_GOAL := preflight

.PHONY: up-access login link-account status up-bootstrap up-network up-cluster up down-cluster down-network down \
        openshell-cli up-agent-sandbox up-openshell down-openshell bastion-cli up-maas \
        up-openclaw-image claw-test deck-live deck-mock deck-zip up-operators up-openshift-ai up-shop up-apprentice up-platform \
        up-mlflow up-traces night up-guardrails campaign cluster-login up-pool dashboard dashboard-stop film up-facts captures up-fd-limit up-tune up-persona up-model-name oracle shell-ui links prepare up-deck

.NOTPARALLEL: up-platform

.PHONY: preflight vendor cli-connect test rosa-cluster-login
test:             ## Offline regression checks (no cluster or credentials)
	python3 -m unittest discover -s tests -v

preflight:        ## Read-only check of everything the build needs: CLIs, .env names, cluster, operators, optional bastion
	@python3 scripts/preflight.py

AGENT_OPS_COMMIT = 7230605c8c0a4cec41c3e39e52e521db5c941355
vendor:           ## Fetch opendatahub-io/agent-ops at the commit we built against (only "make openshell-cli" needs it)
	@test -d vendor/agent-ops/.git || git clone -q https://github.com/opendatahub-io/agent-ops.git vendor/agent-ops
	@git -C vendor/agent-ops checkout -q $(AGENT_OPS_COMMIT) 2>/dev/null || { git -C vendor/agent-ops fetch -q origin && git -C vendor/agent-ops checkout -q $(AGENT_OPS_COMMIT); }
	@echo "vendor/agent-ops at $(AGENT_OPS_COMMIT)"

login:            ## Red Hat login for ROSA (opens a browser; do this yourself)
	rosa login --use-device-code

link-account:     ## Once per new AWS account: let Red Hat's cluster service work in it
	rosa create ocm-role --mode auto --yes
	rosa create user-role --mode auto --yes

status:           ## Current OpenShift cluster
	oc whoami
	oc get clusterversion
	oc get nodes

up-bootstrap:     ## State bucket (keep it between rebuilds)
	$(TF) bootstrap init -input=false
	$(TF) bootstrap apply -input=false -auto-approve

up-network:       ## VPC, subnets, NAT gateway
	$(TF) foundation init -input=false
	$(TF) foundation apply -input=false -auto-approve

up-cluster:       ## ROSA HCP cluster (about 20 minutes)
	$(TF) rosa init -input=false
	$(TF) rosa apply -input=false -auto-approve

up: up-bootstrap up-network up-cluster

down-cluster:     ## Remove the cluster, its roles and OIDC
	$(TF) rosa destroy -input=false -auto-approve

down-network:     ## Remove VPC and NAT gateway
	$(TF) foundation destroy -input=false -auto-approve

down: down-cluster down-network   ## Everything except the state bucket

# ---- Platform on an existing OpenShift cluster (current oc context) ----
up-access:        ## Fresh cluster: cluster-admin (password only in local/ and ~/.olli on the bastion), logins, machine pool olli
	python3 scripts/cluster-access.py

cluster-login:    ## Interactive oc login using the current kubeconfig
	python3 scripts/cluster-login.py

# Honor KUBECONFIG, otherwise use the current oc context (~/.kube/config).
export PATH := $(HOME)/.local/bin:$(PATH)

rosa-cluster-login: ## Optional legacy ROSA login into local/kubeconfig
	python3 scripts/rosa-cluster-login.py

openshell-cli: vendor ## Local OpenShell CLI 0.0.116 (pinned installer, checksum verified)
	bash vendor/agent-ops/scripts/install-openshell-cli.sh

WAIT = bash scripts/wait-for.sh

up-agent-sandbox: ## Red Hat build of Agent Sandbox 0.9
	oc apply -f gitops/01-agent-sandbox/subscription.yaml
	$(WAIT) csv openshift-operators agent-sandbox-operator
	$(WAIT) crd sandboxes.agents.x-k8s.io

up-openshell:     ## OpenShell gateway, narrow SCC and route (then make cli-connect)
	bash gitops/02-openshell/install.sh

cli-connect:      ## Connect the installed OpenShell CLI (local by default)
	python3 scripts/run-openshell.py gitops/02-openshell/connect-cli.sh

bastion-cli:      ## Optional legacy bastion: install and connect OpenShell
	python3 scripts/run-openshell.py gitops/02-openshell/install-cli-linux.sh
	python3 scripts/run-openshell.py gitops/02-openshell/connect-cli.sh

up-maas:          ## Red Hat MaaS model behind inference.local (key stays in the gateway)
	python3 scripts/run-openshell.py gitops/02-openshell/provider-maas.sh

up-openclaw-image: ## Build the OpenClaw sandbox image on the cluster
	oc apply -f gitops/03-openclaw-image/build.yaml
	$(WAIT) sa olli-build builder
	oc start-build openclaw-sandbox -n olli-build --follow

up-operators:     ## OpenShift AI 3.5, cert-manager, LeaderWorkerSet, MCP gateway
	python3 scripts/install-platform-resources.py operators
	$(WAIT) csv redhat-ods-operator rhods-operator 1200
	$(WAIT) csv cert-manager-operator openshift-cert-manager-operator
	$(WAIT) csv openshift-lws-operator leader-worker-set
	$(WAIT) csv openshift-operators mcp-gateway 1200
	$(WAIT) crd datascienceclusters.datasciencecluster.opendatahub.io mcpgatewayextensions.mcp.kuadrant.io mcpserverregistrations.mcp.kuadrant.io

up-openshift-ai:  ## DataScienceCluster with the components the talk uses
	$(WAIT) crd datascienceclusters.datasciencecluster.opendatahub.io
	python3 scripts/install-platform-resources.py openshift-ai
	$(WAIT) crd mlflows.mlflow.opendatahub.io nemoguardrails.trustyai.opendatahub.io
	$(WAIT) exists - gatewayclass/data-science-gateway-class

up-mlflow:        ## MLflow tracking server of OpenShift AI (workspace = namespace)
	$(WAIT) crd mlflows.mlflow.opendatahub.io
	oc apply -f gitops/12-mlflow/mlflow.yaml
	$(WAIT) condition - mlflow/mlflow Available 900

up-traces:        ## Chapter 2: MLflow experiment, access for the scribe, OpenTelemetry collector
	bash gitops/22-traces/install.sh

up-guardrails:    ## Chapter 3: NeMo Guardrails (OpenShift AI) with rails releases 1.5 and 1.5.1
	bash gitops/23-guardrails/install.sh

up-shop:          ## Shop image, shop-tools, tool gateway, model gateway, shop-front
	bash gitops/20-shop/install.sh

up-deck:          ## The deck served from the cluster over HTTPS (scripted for everyone, live with the password on slide 1)
	bash gitops/24-deck/install.sh

up-facts:         ## Versions for the deck's architecture picture, read from the cluster (after an upgrade)
	bash gitops/20-shop/facts.sh

captures:         ## Real product pages for the deck: a trace in MLflow, the rails in the console (you log in to the console once)
	python3 scripts/captures.py

up-apprentice:    ## (Re)create the apprentice sandbox with policy, config and role
	python3 scripts/run-openshell.py gitops/04-openclaw/apprentice.sh gitops/04-openclaw/policy.yaml \
	  gitops/04-openclaw/openclaw.json gitops/04-openclaw/AGENTS.md gitops/04-openclaw/SOUL.md \
	  gitops/04-openclaw/IDENTITY.md gitops/04-openclaw/USER.md
	bash gitops/04-openclaw/fd-limit.sh

up-fd-limit:      ## Room for more open files in every apprentice's OpenShell supervisor (after a sandbox restarted)
	bash gitops/04-openclaw/fd-limit.sh

up-tune:          ## Running apprentices take over changed OpenClaw settings, without being recreated (keeps the audit log)
	python3 scripts/run-openshell.py gitops/04-openclaw/tune.sh

up-persona:       ## Running apprentices take over the persona files (AGENTS, SOUL, IDENTITY, USER), without being recreated
	python3 scripts/run-openshell.py gitops/04-openclaw/persona.sh gitops/04-openclaw/AGENTS.md gitops/04-openclaw/SOUL.md \
	  gitops/04-openclaw/IDENTITY.md gitops/04-openclaw/USER.md

up-model-name:    ## Running apprentices ask for the model as "oracle" (what MLflow and the console then show), without being recreated
	python3 scripts/run-openshell.py gitops/04-openclaw/model-name.sh

up-pool:          ## Chapter 4: two more apprentices for the phones (apprentice-2, apprentice-3)
	for n in 2 3; do APPRENTICE_NAME=apprentice-$$n $(MAKE) up-apprentice; done

up-platform: up-agent-sandbox up-openshell cli-connect up-openclaw-image up-operators up-openshift-ai up-mlflow up-shop up-traces up-guardrails up-maas up-apprentice up-pool up-deck

night:            ## The blond boy's night: 40 tricks against the real apprentice (run the evening before)
	python3 scripts/night.py

campaign:         ## Red-team campaigns against rails 1.5 and 1.5.1 (about 3 to 10 minutes each)
	python3 scripts/campaign.py 1.5 1.5.1

deck-live:        ## Deck demos against the cluster (writes deck/js/config.local.js, holds the desk key)
	python3 scripts/deck-live.py

deck-mock:        ## Deck back to the scripted version
	python3 scripts/deck-live.py --off

deck-zip:         ## Zip the deck for sharing, always without the local live config
	rm -f ollivanders-apprentice-deck.zip && zip -qr ollivanders-apprentice-deck.zip deck -x 'deck/js/config.local.js' -x '*.DS_Store'

film:             ## Cut the intro film from the shots, the text and the sounds, and put it into the deck
	python3 film/cut.py --install

dashboard:        ## The apprentice's own console (OpenClaw Control UI) in your browser, via OpenShell forward
	python3 scripts/dashboard.py $(or $(SANDBOX),apprentice)

dashboard-stop:   ## Close that console: OpenShell forward (and optional SSH tunnel)
	python3 scripts/dashboard.py --stop

shell-ui:         ## OpenShell terminal UI in the current interactive terminal
	python3 scripts/shell-ui.py

prepare:          ## Everything reset and prepared for a run of the talk, about 12 minutes (QUICK=1 without the night run, CAMPAIGN=1 runs the campaigns again, CHECK=1 only looks)
	@python3 scripts/prepare.py $(if $(QUICK),--quick) $(if $(CAMPAIGN),--campaign) $(if $(CHECK),--check)

links:            ## Every address of the demo on one page (SECRETS=1: with the desk key)
	@python3 scripts/links.py $(if $(SECRETS),--secrets) $(if $(OUT),--out $(OUT))

oracle:           ## The three oracles: who answers first, calls, tokens, dollars (scripts/oracle.py mode|mark|since)
	python3 scripts/oracle.py

claw-test:        ## One OpenClaw turn in a throwaway sandbox, plus a blocked internet call
	python3 scripts/run-openshell.py gitops/04-openclaw/smoke-test.sh gitops/04-openclaw/openclaw.json

down-openshell:   ## Remove OpenShell and its namespace
	-helm uninstall openshell -n openshell
	-oc delete -f gitops/02-openshell/00-namespace-scc.yaml
	rm -rf $(HOME)/.config/openshell/gateways/olli
