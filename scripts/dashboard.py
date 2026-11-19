#!/usr/bin/env python3
"""Open the apprentice's own console (OpenClaw's Control UI) in this laptop's browser.

  make dashboard                       # the apprentice behind the shop chat
  make dashboard SANDBOX=apprentice-2  # one of the rush apprentices
  make dashboard-stop                  # close the forward and the tunnel

The Control UI is served by the OpenClaw gateway inside the sandbox, on loopback port 18789.
Nothing on the cluster exposes it: no service, no route. Locally the OpenShell CLI
forwards it directly. With an optional bastion the way in has two legs:

  browser ─ssh tunnel─> bastion 127.0.0.1:18789 ─openshell forward (mTLS)─> sandbox 127.0.0.1:18789

`openclaw dashboard --json` inside the sandbox issues a one-time pairing link, valid for ten
minutes. This script opens it in the default browser and never prints it. That browser keeps an
admin device credential afterwards, so later visits to http://127.0.0.1:18789/ need no link.
Only one apprentice at a time: they all listen on the same port inside their sandboxes.
"""
import json
import os
import shlex
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import webbrowser

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PORT = 18789
POOL = ["apprentice", "apprentice-2", "apprentice-3"]
TUNNEL = ["ssh", "-N", "-f", "-o", "BatchMode=yes", "-o", "ExitOnForwardFailure=yes",
          "-L", f"{PORT}:127.0.0.1:{PORT}"]


def load_env():
    env = {}
    with open(os.path.join(ROOT, ".env")) as f:
        for line in f:
            line = line.rstrip("\n")
            if "=" in line and not line.lstrip().startswith("#"):
                k, v = line.split("=", 1)
                env[k.strip()] = v.strip()
    return env


def run_cli(target, script):
    """Run locally or over SSH. Capture output because it may contain a pairing link."""
    command = ["ssh", "-o", "BatchMode=yes", target, "bash -s"] if target else ["bash", "-s"]
    return subprocess.run(command, text=True, capture_output=True,
                          input="export PATH=$HOME/.local/bin:$PATH NO_COLOR=1\n" + script + "\n")


def stop_forwards(keep=None):
    return "".join(f"openshell forward stop {PORT} {s} >/dev/null 2>&1 || true\n" for s in POOL if s != keep)


def listening():
    with socket.socket() as s:
        s.settimeout(1)
        return s.connect_ex(("127.0.0.1", PORT)) == 0


def stop(target):
    run_cli(target, stop_forwards())
    if target:
        subprocess.run(["pkill", "-f", f"ssh -N -f .*-L {PORT}:127.0.0.1:{PORT}"], check=False)
    print("Console closed: OpenShell forward stopped.")


def main():
    args = sys.argv[1:]
    env = load_env()
    if bool(env.get("BASTION_HOST")) != bool(env.get("BASTION_USER")):
        sys.exit("Set both BASTION_HOST and BASTION_USER, or neither.")
    target = f"{env['BASTION_USER']}@{env['BASTION_HOST']}" if env.get("BASTION_HOST") else None
    if target and target.startswith("-"):
        sys.exit("Invalid bastion SSH target")
    if args == ["--stop"]:
        return stop(target)
    # --capture [options for scripts/capture-ui.mjs]: take a picture of the console for the deck
    capture = None
    if "--capture" in args:
        i = args.index("--capture")
        capture, args = args[i + 1:], args[:i]
    name = args[0] if args else "apprentice"
    if name not in POOL:
        sys.exit(f"Unknown sandbox {name!r}. One of: {', '.join(POOL)}")
    q = shlex.quote(name)

    # 1. On the CLI host: one forward, for this apprentice only. Make sure its gateway runs, then
    #    ask OpenClaw for a pairing link. Everything but the JSON goes to stderr. The forward keeps
    #    running after this ssh session; it must not hold the session's output open, or ssh never
    #    returns (it did exactly that on the first real run), so its output goes nowhere.
    r = run_cli(target, stop_forwards() + f"""
openshell forward start {PORT} {q} -d </dev/null >/dev/null 2>&1 || exit 11
openshell sandbox exec -n {q} --no-tty -- sh /sandbox/.openclaw/start-gateway.sh </dev/null >&2 || exit 12
openshell sandbox exec -n {q} --no-tty -- openclaw dashboard --json </dev/null
""")
    if r.returncode in (11, 12):
        step = "port forward" if r.returncode == 11 else "gateway start"
        sys.exit(f"The {step} in sandbox {name} failed:\n{r.stderr.strip()[-1500:]}")
    link = None
    for line in reversed(r.stdout.splitlines()):
        if line.strip().startswith("{"):
            try:
                link = json.loads(line)
            except ValueError:
                pass
            break
    if not link or not link.get("browserUrl"):
        reason = (link or {}).get("reason") or f"no JSON from openclaw dashboard (exit {r.returncode})"
        sys.exit(f"No pairing link from the gateway in {name}: {reason}\n{r.stderr.strip()[-800:]}")
    url = link["browserUrl"]
    where = urllib.parse.urlsplit(url)
    if where.hostname not in ("127.0.0.1", "localhost") or (where.port or 80) != PORT:
        sys.exit(f"The pairing link points at {where.hostname}:{where.port}, not 127.0.0.1:{PORT}. "
                 "Check gateway.bind and gateway.port in gitops/04-openclaw/openclaw.json.")

    # 2. On this laptop: the ssh tunnel to the bastion, unless one is up already.
    if target and not listening():
        subprocess.run(TUNNEL + [target], check=True)

    # 3. Wait until the Control UI answers through both legs, then open the one-time link.
    for _ in range(30):
        try:
            urllib.request.urlopen(f"http://127.0.0.1:{PORT}/", timeout=3)
            break
        except urllib.error.HTTPError:
            break                       # any HTTP answer means the gateway is on the other end
        except (urllib.error.URLError, OSError):
            time.sleep(1)
    else:
        sys.exit(f"Nothing answers on http://127.0.0.1:{PORT}/ after 30 s. Try make dashboard-stop, then again.")
    if capture is not None:
        # For the deck: the console refuses to be framed (X-Frame-Options: DENY), so the slide shows a
        # capture. The one-time link goes to the capture tool through the environment, never as an
        # argument, and pairs a throwaway headless browser instead of yours.
        r = subprocess.run(["node", os.path.join(ROOT, "scripts", "capture-ui.mjs"), "console", "-", *capture],
                           env=dict(os.environ, CAPTURE_URL=url))
        sys.exit(r.returncode)
    webbrowser.open(url)
    print(f"The console of {name} is open in your browser: http://127.0.0.1:{PORT}/\n"
          "That browser stays paired. make dashboard-stop closes forward and tunnel.")


if __name__ == "__main__":
    main()
