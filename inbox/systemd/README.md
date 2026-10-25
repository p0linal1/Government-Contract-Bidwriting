# systemd (Linux) scheduling for the bid inbox and the sourcing search

User-level units (no root; run with your browser profiles and `~/.config/bidkit` secrets).

```
mkdir -p ~/.config/systemd/user
sed "s|%h/bid-writing|$HOME/bid-writing|g" inbox/systemd/bid-inbox.service > ~/.config/systemd/user/bid-inbox.service
cp inbox/systemd/bid-inbox.timer ~/.config/systemd/user/
sed "s|%h/bid-writing|$HOME/bid-writing|g" inbox/systemd/bid-source.service > ~/.config/systemd/user/bid-source.service
cp inbox/systemd/bid-source.timer ~/.config/systemd/user/
systemctl --user daemon-reload
systemctl --user enable --now bid-inbox.timer bid-source.timer
loginctl enable-linger "$USER"        # timers keep running after you log out
```
`bid-source.timer` fires weekdays at 07:15 and runs `bin/bid-source.sh` (FGA sourcing; needs the
FGA tokens bootstrapped once — see the service file header). Notifications on Linux: the script
uses `osascript` (macOS only); add `notify-send` in `bin/bid-source.sh` if wanted.

Check / operate:
```
systemctl --user list-timers bid-inbox.timer
systemctl --user start bid-inbox.service         # run now
journalctl --user -u bid-inbox -n 50 --no-pager  # unit log (the poller also writes inbox/logs/YYYY-MM.log)
```

Notes
- `bid-inbox.service` is `Type=oneshot`; the timer fires it every 30 min on weekdays 07:00–19:30.
  `Persistent=true` catches up a missed run after sleep/shutdown.
- Portal autofetch runs headless and needs no display, but the per-portal login must be done
  once on a machine with a display (`python3 -m bidkit.portal login <domain>`), then the
  profile directory (including `storage_state.json`) can be copied to
  `~/.config/bidkit/browser-profiles/<portal>/` on this machine (chmod 700).
- If the machine also runs a desktop session, the desktop notification in
  `inbox/hooks/on-new-opportunity.sh` uses `osascript` (macOS only) and is skipped here;
  add `notify-send` if wanted.
