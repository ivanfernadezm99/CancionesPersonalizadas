#!/usr/bin/env python3
"""Mint a short-lived service JWT for the FileManager backup cron.

Reads ``JWT_SHARED_SECRET`` from the environment and emits a single HS256 token
on stdout. Used by ``backup_to_filemanager.sh`` to authenticate against
ECFileManager (once JWT validation is enforced there).
"""

from __future__ import annotations

import datetime
import os
import sys

from jose import jwt

SECRET_ENV = "JWT_SHARED_SECRET"
ISSUER = "canciones-backup"
AUDIENCE = "ecfilemanager"


def main() -> int:
    secret = os.environ.get(SECRET_ENV)
    if not secret:
        print(f"error: falta {SECRET_ENV} en el entorno", file=sys.stderr)
        return 1

    now = datetime.datetime.now(datetime.timezone.utc)
    claims = {
        "sub": "canciones-backup-service",
        "role": "ServiceAccount",
        "IsServiceToken": "true",
        "iss": ISSUER,
        "aud": AUDIENCE,
        "iat": int(now.timestamp()),
        "exp": int((now + datetime.timedelta(hours=1)).timestamp()),
    }
    print(jwt.encode(claims, secret, algorithm="HS256"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
