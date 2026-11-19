#!/usr/bin/env python3
"""Switch the deck to live mode for the current cluster.

Writes deck/js/config.local.js with the shop's address and the desk key, read from the cluster
(the current oc context). The file is in .gitignore and must not go into the shared zip.
Delete it (make deck-mock) and the deck is the scripted version again.

  scripts/deck-live.py --hosted FILE   the config for the deck served from the cluster
                                       (gitops/24-deck): the same addresses, no key, and
                                       where to trade the password for the key
"""
from _oc import oc_out
import base64
import json
import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "deck", "js", "config.local.js")


KEY = "__DESK_KEY__"
# The hosted deck's config. With a key (from the link, remembered by this browser) the deck runs
# live; without one this file changes nothing and the deck stays the scripted version.
HOSTED = """// Written by scripts/deck-live.py --hosted for the deck served from the cluster. No key and no
// password in here. The key comes from the shop, in exchange for the password typed on slide 1
// (or from a link, …/#key=…), and is kept in this browser. "…/#key=" (empty) forgets it.
(function () {
  var m = /[#&]key=([0-9A-Za-z_-]*)/.exec(location.hash), key = m ? m[1] : "";
  try {
    if (m) { if (key) localStorage.setItem("olli-desk-key", key); else localStorage.removeItem("olli-desk-key"); }
    else key = localStorage.getItem("olli-desk-key") || "";
  } catch (e) { /* private window: the key lasts for this page */ }
  // The link with the key pasted into a tab that already shows the deck only changes the hash.
  window.addEventListener("hashchange", function () { if (/[#&]key=/.test(location.hash)) location.reload(); });
  if (m && history.replaceState) history.replaceState(null, "", location.pathname + location.search);
  // Where slide 1 sends the password. The shop checks it and answers with the key.
  window.OLLI_CONFIG.loginUrl = "__LOGIN_URL__";
  if (!key) return;
  var live = LIVE;
  Object.keys(live).forEach(function (k) { live[k] = live[k].split("__DESK_KEY__").join(key); });
  Object.assign(window.OLLI_CONFIG, live);
})();
"""


def oc(*args):
    env = dict(os.environ)
    return oc_out(args, env=env)


def main():
    if len(sys.argv) > 1 and sys.argv[1] == "--off":
        if os.path.exists(OUT):
            os.remove(OUT)
        print("deck is back to the scripted version")
        return
    hosted = sys.argv[2] if len(sys.argv) > 2 and sys.argv[1] == "--hosted" else ""
    host = oc("get", "route", "shop", "-n", "ollivanders", "-o", "jsonpath={.spec.host}").strip()
    # The hosted deck (gitops/24-deck) is open to everyone, so its config holds a placeholder
    # instead of the key; the key comes from the shop for the password typed on slide 1
    # (POST /api/deck-login), or from the link the presenter opens (…/#key=…).
    key = KEY if hosted else base64.b64decode(json.loads(oc("get", "secret", "shop-tokens", "-n", "ollivanders", "-o", "json"))["data"]["desk"]).decode()
    origin = f"https://{host}"
    # The OpenShift console, for the deck's links into it (topology, the rails' config maps).
    console = oc("whoami", "--show-console").strip().rstrip("/")
    live = {
        "mode": "live",
        "shopOrigin": origin,
        "shopChatUrl": f"{origin}/?embed=1&solo=1",
        "deskUrl": f"{origin}/desk?embed=1#key={key}",
        # The apprentice's own console. Not on the cluster: "make dashboard" brings it to this
        # laptop's loopback. Open the deck at http://127.0.0.1:8765 so frame and deck share one site.
        "consoleUrl": "http://127.0.0.1:18789/",
        "mlflowTraceUrl": f"{origin}/scroll?embed=1#key={key}",
        "guardChatUrl": f"{origin}/?embed=1&solo=1&who=customer",
        "railsUrl": f"{origin}/rails?embed=1#key={key}",
        "campaignUrl": f"{origin}/campaign?embed=1#key={key}",
        "backstageUrl": f"{origin}/backstage?embed=1#key={key}",
        "audienceUrl": f"{host}/phone",
        "audienceQrImage": f"{origin}/qr.svg",
        "audiencePhoneUrl": f"{origin}/phone",
        "rushStatsUrl": f"{origin}/api/rush",
        "consoleBase": console,
    }
    if hosted:
        with open(hosted, "w") as f:
            f.write(HOSTED.replace("__LOGIN_URL__", f"{origin}/api/deck-login").replace("LIVE", json.dumps(live, indent=2)))
        print(f"hosted deck config written for {origin} (no key in it)")
        return
    with open(OUT, "w") as f:
        f.write("// Written by scripts/deck-live.py for the current cluster. Holds the desk key:\n")
        f.write("// not in git, not in the zip. \"make deck-mock\" removes it.\n")
        f.write("Object.assign(window.OLLI_CONFIG, " + json.dumps(live, indent=2) + ");\n")
    os.chmod(OUT, 0o600)
    print(f"deck is live against {origin}")


if __name__ == "__main__":
    main()
