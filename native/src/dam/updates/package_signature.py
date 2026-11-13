"""Ed25519 signatures for this app’s native release archives."""
import base64
import binascii
import os
from pathlib import Path
import sys

from Cryptodome.Signature import eddsa


def _decode(value, length, what):
    try:
        raw = base64.b64decode(value.strip(), validate=True)
    except (ValueError, binascii.Error, AttributeError):
        raise ValueError(f"Invalid {what}.") from None
    if len(raw) != length:
        raise ValueError(f"Invalid {what}.")
    return raw


def sign(data, pair):
    """Sign with the release key, given as base64 of its 32-byte seed and 32-byte public key."""
    raw = _decode(pair, 64, "signing key")
    key = eddsa.import_private_key(raw[:32])
    if key.public_key().export_key(format="raw") != raw[32:]:
        raise ValueError("Invalid signing key.")
    return base64.b64encode(eddsa.new(key, "rfc8032").sign(data)).decode("ascii")


def verify(data, signature, public_key):
    try:
        key = eddsa.import_public_key(_decode(public_key, 32, "public key"))
        eddsa.new(key, "rfc8032").verify(data, _decode(signature, 64, "signature"))
    except ValueError:
        return False
    return True


def main(argv):
    """Sign a release package in CI: writes <package>.sig and checks it against the public key."""
    if len(argv) != 3:
        print("Usage: package_signature.py PACKAGE PUBLIC_KEY_FILE", file=sys.stderr)
        return 2
    package, public_key = Path(argv[1]), Path(argv[2]).read_text()
    data = package.read_bytes()
    try:
        signature = sign(data, os.environ["DAM_UPDATE_PRIVATE_KEY"])
    except (KeyError, ValueError):
        # Never echo key material.
        print("The update signing key is missing or invalid.", file=sys.stderr)
        return 1
    if not verify(data, signature, public_key):
        print("The signing key does not match the published public key.", file=sys.stderr)
        return 1
    package.with_name(package.name + ".sig").write_text(signature + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
