#!/bin/sh
set -eu
# A Certbot deploy hook; unrelated certificates do not reload nginx here.
if [ "${RENEWED_LINEAGE:-}" = /etc/letsencrypt/live/api.mambovipi.app ]; then
    /usr/sbin/nginx -t
    /usr/bin/systemctl reload nginx
fi
