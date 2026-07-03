# Security notes

This project touches camera feeds and your home network. A few rules:

- **Never commit secrets.** No camera passwords, RTSP URLs with credentials,
  WireGuard/`.conf`/`.key` files, ntfy tokens, TLS keys, or databases. They are
  gitignored, but double-check before every push.
- **Keep real config out of git.** Commit `examples/go2rtc.example.yaml` and
  `.env.example` with placeholder values; keep your real `go2rtc.yaml` / `.env`
  local (both are gitignored).
- **Don't expose this to the internet directly.** The viewer and go2rtc have no
  auth by design — reach them over a VPN (WireGuard/Tailscale) or a
  reverse proxy with authentication, not a raw port-forward.
- **Scan before you publish.** Run a secret scanner on the whole tree, e.g.:
  ```
  gitleaks detect --source . --no-git
  ```

Found a vulnerability? Please open a private report / security advisory rather
than a public issue.
