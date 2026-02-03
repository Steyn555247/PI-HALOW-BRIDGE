# Problem Summary + Claude Prompt: Improve Bridge Connectivity

## What the logs show (problem)

- **Robot Pi** is configured with **BASE_PI_IP=172.20.10.2** and tries to connect to Base Pi at that address for telemetry (5003) and video (5002).
- **Result:** "Failed to connect to Base Pi telemetry: timed out" and "Failed to connect to Base Pi video: timed out" — the Robot Pi never reaches the Base Pi on those ports.

So either:

1. **Wrong IP** — The Base Pi is not at 172.20.10.2 (e.g. it's at 10.103.198.124 or 172.20.10.1). The user must set BASE_PI_IP to the **actual** Base Pi IP (from `hostname -I` on the Base Pi).
2. **Different networks** — Robot Pi is on 172.20.10.x and Base Pi is on another subnet (e.g. 10.103.x.x). They must be on the **same LAN** (same Wi‑Fi or same wired network) to talk.
3. **Base Pi not listening** — The Base Pi's serpent-base-bridge service isn't running or isn't listening on 5002/5003. On Base Pi: `sudo systemctl status serpent-base-bridge` and `ss -tlnp | grep -E '5002|5003'`.
4. **Firewall** — Base Pi firewall (e.g. UFW) is blocking 5002/5003. Open them: `sudo ufw allow 5002/tcp` and `sudo ufw allow 5003/tcp`.

**Quick fix for the user:** On Base Pi run `hostname -I` and use the first IP. On Robot Pi run `sudo bash scripts/set_bridge_ip.sh --robot <BASE_PI_IP>`. Ensure both Pis are on the same network. On Base Pi ensure the bridge is running and ports 5002/5003 are open.

---

## Copy-paste prompt for Claude

Use this in a new chat with Claude (with the pi_halow_bridge repo in context). Claude should implement the improvements and you can then push to GitHub.

```
In the Pi HaLow Bridge repo (pi_halow_bridge), improve connectivity and diagnostics so users can quickly see why the bridge fails to connect (wrong IP, different network, Base Pi not listening, firewall).

## Current problem

The Robot Pi bridge connects to the Base Pi using BASE_PI_IP (telemetry port 5003, video port 5002). When the IP is wrong or the Pis are on different networks, the logs show "Failed to connect to Base Pi telemetry: timed out" and "Failed to connect to Base Pi video: timed out" with no clear guidance. Users also see errno 101 "Network is unreachable" when the destination subnet is not routable. The Base Pi side does not log the configured ROBOT_PI_IP or whether it is reachable.

## 1. Log configured IPs at startup (both Pis)

- **Robot Pi** (robot_pi/halow_bridge.py or main entry): At startup, log the configured BASE_PI_IP and the ports used (e.g. "Connecting to Base Pi at <BASE_PI_IP>:5002 (video), <BASE_PI_IP>:5003 (telemetry)"). Use the value from config (already read from environment).
- **Base Pi** (base_pi/halow_bridge.py or main entry): At startup, log the configured ROBOT_PI_IP (and optionally CONTROL_PORT if the Base Pi initiates something to the Robot). So users can confirm in the logs which IP the service is using.

## 2. Clearer error messages when connection fails

- When the Robot Pi fails to connect to Base Pi (telemetry or video), in addition to "Failed to connect... timed out", log a short hint: e.g. "Check: (1) Base Pi IP is correct (run hostname -I on Base Pi). (2) Both Pis on same network. (3) Base Pi bridge is running: systemctl status serpent-base-bridge. (4) Base Pi firewall allows 5002, 5003."
- When the error is errno 101 (Network is unreachable), log a hint that the destination IP may be on a different network and both Pis must be on the same LAN.

Implement this in the existing log messages (e.g. in telemetry and video connection failure paths in the Robot Pi code, and any place that catches socket errors). Prefer a single helper that formats the hint so it's consistent.

## 3. Optional: pre-flight connectivity check script

- Add a small script (e.g. scripts/check_bridge_connectivity.sh) that:
  - Takes --robot or --base (or detects).
  - On Robot Pi: reads BASE_PI_IP from config or /etc/serpent/base_pi_ip, then pings that IP and optionally runs nc -zv BASE_PI_IP 5002 and nc -zv BASE_PI_IP 5003; reports success/failure and suggests fixes (wrong IP, same network, Base Pi service, firewall).
  - On Base Pi: reads ROBOT_PI_IP from config or /etc/serpent/robot_pi_ip, pings it, reports success/failure.
  - So the user can run it before or after starting the bridge to verify connectivity. Document it in SETUP_SECOND_PI.md or README.

If implementing the script, use the same persistent IP files as set_bridge_ip.sh (/etc/serpent/base_pi_ip, /etc/serpent/robot_pi_ip) when present; otherwise fall back to defaults or prompt.

## 4. Documentation

- In SETUP_SECOND_PI.md (or the main setup doc), add a short "Troubleshooting: Connection timeouts / Network unreachable" section that says:
  - Confirm both Pis are on the same network (same Wi‑Fi or same switch).
  - On Base Pi run hostname -I and use that IP as BASE_PI_IP on the Robot Pi (set_bridge_ip.sh --robot <ip>).
  - On Robot Pi run hostname -I and use that IP as ROBOT_PI_IP on the Base Pi (set_bridge_ip.sh --base <ip>).
  - If connection times out: Base Pi bridge must be running and listening on 5002, 5003; open firewall if needed (ufw allow 5002/tcp 5003/tcp).
  - Optionally mention the check_bridge_connectivity.sh script if you add it.

Implement the logging and error-message improvements in the Python code; add the optional script and doc updates as described. After your changes, the repo should be in a state ready to push to GitHub (no broken tests, clear commit message).
```

---

Use the **Copy-paste prompt for Claude** block in a new Claude chat with the repo in context. After Claude applies the changes, push to GitHub as usual.
