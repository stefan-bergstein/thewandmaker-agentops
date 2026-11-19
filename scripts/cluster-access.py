#!/usr/bin/env python3
"""Get access to a fresh ROSA cluster, as code. Idempotent: run it again any time.

    python3 scripts/cluster-access.py                  # what "make up-access" runs
    python3 scripts/cluster-access.py --recreate-admin # admin exists, but its password is lost

1. Finds the cluster name (rosa list clusters on the bastion, matched against ROSA_API_URL).
2. Creates the cluster-admin user if there is none ("rosa create admin" on the bastion). The
   password is cut out of rosa's output on the bastion itself and stored in ~/.olli/cluster-admin
   there (umask 077) and in local/cluster-admin-password here (mode 0600). It is never printed.
   The bastion file is the source of truth: the bastion belongs to this cluster, a local file may
   be left over from an earlier one.
3. Waits until the login works (a new admin needs a few minutes), refreshes local/kubeconfig with
   scripts/rosa-cluster-login.py and logs oc in on the bastion as well.
4. Creates the machine pool "olli" (3 x m6a.2xlarge, label olli.dev/pool=work) if it is missing
   and waits until its three nodes are Ready.
"""
import json
import os
import re
import shlex
import subprocess
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOCAL_PW = os.path.join(ROOT, "local", "cluster-admin-password")
KUBECONFIG = os.path.join(ROOT, "local", "kubeconfig")
POOL = {"name": "olli", "replicas": 3, "type": "m6a.2xlarge", "label": "olli.dev/pool=work"}


def load_env():
    env = {}
    with open(os.path.join(ROOT, ".env")) as f:
        for line in f:
            m = re.match(r"^([A-Za-z_][A-Za-z0-9_]*)=(.*)$", line.strip())
            if m:
                env[m.group(1)] = m.group(2).strip()
    return env


ENV = load_env()
TARGET = f"{ENV['BASTION_USER']}@{ENV['BASTION_HOST']}"
API = ENV["ROSA_API_URL"]


def say(msg):
    print(f"[access {time.strftime('%H:%M:%S')}] {msg}", flush=True)


def remote(script, check=True):
    """Run a bash script on the bastion (over stdin, so nothing lands in a command line here)."""
    r = subprocess.run(["ssh", "-o", "BatchMode=yes", TARGET, "bash -s"],
                       input="set -euo pipefail\nexport PATH=$HOME/.local/bin:$PATH NO_COLOR=1\n" + script,
                       text=True, capture_output=True)
    if check and r.returncode != 0:
        sys.exit(f"bastion step failed ({r.returncode}):\n{r.stdout[-1500:]}{r.stderr[-1500:]}")
    return r


def cluster_name():
    out = remote("rosa list clusters -o json").stdout
    host = API.split("//", 1)[-1].split(":")[0]           # api.cluster.example.com
    for c in json.loads(out or "[]"):
        url = (c.get("api") or {}).get("url", "")
        if c.get("name") and (host in url or f".{c['name']}." in host):
            return c["name"]
    m = re.match(r"api\.([^.]+)\.", host)
    if m:
        return m.group(1)
    sys.exit(f"no cluster found for {API}")


def admin_exists(cluster):
    out = remote(f"rosa describe admin -c {shlex.quote(cluster)} 2>&1 || true").stdout
    return "There is no" not in out


def bastion_has_password():
    return remote("test -s ~/.olli/cluster-admin && echo yes || echo no").stdout.strip() == "yes"


def create_admin(cluster):
    say(f"creating cluster-admin on {cluster} (rosa create admin)")
    # The password is cut out on the bastion; every line that contains it is dropped before printing.
    r = remote(f"""umask 077; mkdir -p ~/.olli
out=$(rosa create admin -c {shlex.quote(cluster)} 2>&1) || {{ printf '%s\\n' "$out" | grep -v -- '--password'; exit 1; }}
pw=$(printf '%s\\n' "$out" | sed -n 's/.*--password[ =]\\([^ ]*\\).*/\\1/p' | head -1)
if [ -z "$pw" ]; then printf '%s\\n' "$out" | grep -v -- '--password'; echo "no password found in rosa's output"; exit 1; fi
printf '%s' "$pw" > ~/.olli/cluster-admin
printf '%s\\n' "$out" | grep -vF -- "$pw" | grep -v -- '--password' | sed 's/^/  /'
""")
    print(r.stdout.rstrip())


def copy_password_here():
    r = subprocess.run(["ssh", "-o", "BatchMode=yes", TARGET, "cat ~/.olli/cluster-admin"],
                       capture_output=True, text=True, check=True)
    pw = r.stdout.strip()
    if not pw:
        sys.exit("empty password file on the bastion")
    os.makedirs(os.path.dirname(LOCAL_PW), exist_ok=True)
    old = open(LOCAL_PW).read().strip() if os.path.exists(LOCAL_PW) else None
    if old != pw:
        if os.path.exists(LOCAL_PW):
            os.remove(LOCAL_PW)
        fd = os.open(LOCAL_PW, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "w") as f:
            f.write(pw + "\n")
        say("local/cluster-admin-password written (0600)")
    os.chmod(LOCAL_PW, 0o600)


def kube_ok():
    env = dict(os.environ, KUBECONFIG=KUBECONFIG)
    r = subprocess.run(["oc", "whoami", "--show-server"], env=env, capture_output=True, text=True)
    if r.returncode != 0 or r.stdout.strip().rstrip("/") != API.rstrip("/"):
        return False
    r = subprocess.run(["oc", "whoami"], env=env, capture_output=True, text=True)
    return r.returncode == 0 and r.stdout.strip() == "cluster-admin"


def login_local(wait_s=1500):
    if kube_ok():
        say("local/kubeconfig works")
        return
    if os.path.exists(KUBECONFIG):
        os.remove(KUBECONFIG)                     # stale (other cluster or expired token)
        say("removed the stale local/kubeconfig")
    t0 = time.time()
    while True:
        r = subprocess.run([sys.executable, os.path.join(ROOT, "scripts", "cluster-login.py")],
                           capture_output=True, text=True)
        if r.returncode == 0 and kube_ok():
            os.chmod(KUBECONFIG, 0o600)
            say(f"logged in as cluster-admin after {int(time.time() - t0)} s; local/kubeconfig refreshed")
            return
        if time.time() - t0 > wait_s:
            print(r.stdout[-400:])
            sys.exit("login still fails. If the admin is older than 30 minutes, its password is stale: "
                     "run 'python3 scripts/cluster-access.py --recreate-admin'.")
        time.sleep(30)


def login_bastion():
    r = remote(f"""oc whoami --show-server 2>/dev/null | grep -qF {shlex.quote(API.split(':443')[0])} && oc whoami 2>/dev/null | grep -qx cluster-admin && {{ echo "bastion oc: already logged in"; exit 0; }}
for i in $(seq 1 30); do
  oc login {shlex.quote(API)} -u cluster-admin -p "$(cat ~/.olli/cluster-admin)" >/dev/null 2>&1 && {{ echo "bastion oc: logged in as $(oc whoami)"; exit 0; }}
  sleep 20
done
echo "bastion oc: login failed"; exit 1
""")
    say(r.stdout.strip())


def oc_json(*args):
    env = dict(os.environ, KUBECONFIG=KUBECONFIG)
    r = subprocess.run(["oc", *args, "-o", "json"], env=env, capture_output=True, text=True)
    return json.loads(r.stdout) if r.returncode == 0 and r.stdout.strip() else {}


def ensure_pool(cluster):
    pools = json.loads(remote(f"rosa list machinepools -c {shlex.quote(cluster)} -o json").stdout or "[]")
    if any(p.get("id") == POOL["name"] for p in pools):
        say(f"machine pool {POOL['name']} exists")
    else:
        say(f"creating machine pool {POOL['name']}: {POOL['replicas']} x {POOL['type']}, label {POOL['label']}")
        r = remote(f"rosa create machinepool -c {shlex.quote(cluster)} --name {POOL['name']} "
                   f"--replicas {POOL['replicas']} --instance-type {POOL['type']} --labels {POOL['label']} 2>&1")
        print(r.stdout.rstrip())


def wait_pool(wait_s=2700):
    t0 = time.time()
    last = None
    while True:
        nodes = oc_json("get", "nodes", "-l", POOL["label"]).get("items", [])
        ready = sum(1 for n in nodes for c in n["status"].get("conditions", [])
                    if c["type"] == "Ready" and c["status"] == "True")
        if ready != last:
            say(f"pool nodes Ready: {ready}/{POOL['replicas']}")
            last = ready
        if ready >= POOL["replicas"]:
            return
        if time.time() - t0 > wait_s:
            sys.exit("machine pool nodes not Ready in time")
        time.sleep(30)


def main():
    recreate = "--recreate-admin" in sys.argv[1:]
    cluster = cluster_name()
    say(f"cluster {cluster} ({API})")
    exists = admin_exists(cluster)
    have = bastion_has_password()
    if exists and not have:
        if not recreate:
            sys.exit("cluster-admin exists, but there is no password in ~/.olli/cluster-admin on the bastion. "
                     "Fix: python3 scripts/cluster-access.py --recreate-admin (rosa delete admin, then create again).")
        say("--recreate-admin: deleting the cluster-admin whose password we don't have")
        remote(f"rosa delete admin -c {shlex.quote(cluster)} --yes 2>&1")
        time.sleep(20)
        exists = False
    if not exists:
        create_admin(cluster)
    else:
        say("cluster-admin exists; password from ~/.olli/cluster-admin on the bastion")
    copy_password_here()
    ensure_pool(cluster)          # rosa side; the nodes come up while we wait for the login
    login_local()
    login_bastion()
    wait_pool()
    say("access ready")


if __name__ == "__main__":
    main()
