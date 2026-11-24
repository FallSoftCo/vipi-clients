# Vipi waitlist service

This service is limited to the public marketing launch list. It does not share the Vipi app API, database, credentials, or process.

## Runtime

- Bind: `127.0.0.1:9876`
- Database: `/var/lib/vipi-waitlist/waitlist.sqlite3`
- Public route: `POST https://mambovipi.app/api/waitlist`
- Health route (loopback only through the service): `GET /healthz`

## Install

1. Create a system user `vipi-waitlist` with home `/var/lib/vipi-waitlist` and no login shell.
2. Install an immutable source release under `/opt/vipi-waitlist/releases/` and point `/opt/vipi-waitlist/current` at it.
3. Install `vipi-waitlist.service`, run `systemctl daemon-reload`, enable the unit, then start it.
4. Add the exact `/api/waitlist` proxy location to the Vipi apex Nginx config and allow `connect-src 'self'; form-action 'self'` in the CSP.

## Test

```sh
python3 -m unittest -v test_app.py
curl -fsS http://127.0.0.1:9876/healthz
```

## Operator export

Run `python3 export_waitlist.py` as root or as the service user. The script writes CSV to stdout. Treat the output as personal data and delete temporary copies after use.
