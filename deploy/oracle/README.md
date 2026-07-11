# XenAlgo Oracle Paper Host Deployment

This kit deploys XenAlgo to the Oracle Cloud Always Free paper VM in paper mode only.
It does not enable live trading, does not enable the Fyers order API, and does not open
the operator console to the public internet.

## Preconditions

- Run only outside NSE market hours.
- SSH access to the Oracle Linux 9 VM as `opc`.
- Tailscale auth handled by the operator in a browser or device approval flow.
- A host-local `/etc/xenalgo/xenalgo.env` with real secret values. Never commit it.

The current documented paper host is:

```powershell
ssh -i <path-to-downloaded-private-key> opc@80.225.212.3
```

If SSH times out, re-check the ephemeral OCI public IP and the OCI security list.
If TCP/22 is open but SSH times out during banner exchange, the micro VM may be overloaded by
package installation. Recover or reboot the instance from OCI, then reconnect and inspect
`/tmp/xenalgo-bootstrap.log` before retrying.

## Deploy From The VM

Copy or clone the repository to `/opt/xenalgo/app`, then run:

```bash
cd /opt/xenalgo/app
sudo bash deploy/oracle/bootstrap_oracle_linux9.sh
sudo cp deploy/oracle/xenalgo.env.example /etc/xenalgo/xenalgo.env
sudo chmod 600 /etc/xenalgo/xenalgo.env
sudo vi /etc/xenalgo/xenalgo.env
```

After Tailscale is up, set `TAILSCALE_BIND_HOST` in `/etc/xenalgo/xenalgo.env` to the
host's Tailscale IP, keep `LIVE_TRADING_ENABLED=false` style application config unchanged,
then start the console:

```bash
tailscale ip -4
sudo systemctl enable --now xenalgo-paper.service
sudo systemctl status xenalgo-paper.service --no-pager
journalctl -u xenalgo-paper.service -n 100 --no-pager
```

## Safety Checks

```bash
docker run --rm xenalgo:oracle-paper python -m xenalgo --profile live
sudo firewall-cmd --list-all
sudo ss -ltnp
```

Expected posture:

- `python -m xenalgo --profile live` prints config checksum metadata.
- SSH is the only public inbound service.
- The console listens on the Tailscale IP and port `8080`.
- `config/config.live.yaml` keeps `live_trading.enabled: false`.
- `config/config.live.yaml` keeps `broker.order_api_enabled: false`.
- The console has no public postback route; live fills use Fyers Order WebSocket plus REST
  orderbook polling, while commissioning fills remain paper-only.

## 2026-07-09 Attempt Note

The first operator-approved deployment attempt restored SSH and copied the app to
`/opt/xenalgo/app`, but the bootstrap overloaded the `VM.Standard.E2.1.Micro` instance during
`dnf install`. Docker, Tailscale, and the systemd unit were not confirmed installed. Recopy
the latest bundle before retrying so the fixed bootstrap time guard is on the host.
