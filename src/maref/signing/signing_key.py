from __future__ import annotations

import base64
import getpass
import os
import stat
from pathlib import Path

from maref.crypto.ed25519_keys import Ed25519KeyPair
from maref.security.decorators import security_critical

_KEY_PURPOSE = "maref-report-signing"


def _encrypt_private_key(pem: str, password: str) -> str:
    from cryptography.hazmat.primitives import serialization

    key = serialization.load_pem_private_key(pem.encode("utf-8"), password=None)
    encrypted = key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.BestAvailableEncryption(password.encode("utf-8")),
    )
    return encrypted.decode("utf-8")


def _decrypt_private_key(encrypted_pem: str, password: str) -> str:
    from cryptography.hazmat.primitives import serialization

    key = serialization.load_pem_private_key(
        encrypted_pem.encode("utf-8"), password=password.encode("utf-8")
    )
    unencrypted = key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )
    return unencrypted.decode("utf-8")


class ReportSigningKey:
    _key: Ed25519KeyPair

    def __init__(self, key_pair: Ed25519KeyPair) -> None:
        self._key = key_pair

    @classmethod
    def generate(cls) -> ReportSigningKey:
        return cls(Ed25519KeyPair.generate())

    @classmethod
    def from_encrypted_private_key_file(
        cls, path: str | Path, password: str | None = None
    ) -> ReportSigningKey:
        key_path = Path(path)
        if password is None:
            password = getpass.getpass(f"Password for {key_path}: ")
        encrypted = key_path.read_text("utf-8")
        decrypted = _decrypt_private_key(encrypted, password)
        return cls.from_private_pem(decrypted)

    def save_encrypted_private_key(self, path: str | Path, password: str | None = None) -> None:
        if password is None:
            password = getpass.getpass("New encryption password: ")
            confirm = getpass.getpass("Confirm password: ")
            if password != confirm:
                raise ValueError("Passwords do not match")
        key_path = Path(path)
        encrypted = _encrypt_private_key(self.private_key_pem, password)
        key_path.write_text(encrypted, encoding="utf-8")
        key_path.chmod(0o600)

    @classmethod
    def from_private_key_file(
        cls, path: str | Path, check_permissions: bool = True, password: str | None = None
    ) -> ReportSigningKey:
        key_path = Path(path)
        if check_permissions:
            cls._check_key_permissions(key_path)
        pem = key_path.read_text("utf-8")
        if "ENCRYPTED" in pem or password is not None:
            pwd = password or getpass.getpass(f"Password for {key_path}: ")
            decrypted = _decrypt_private_key(pem, pwd)
            return cls.from_private_pem(decrypted)
        return cls.from_private_pem(pem)

    @classmethod
    def from_private_pem(cls, private_key_pem: str) -> ReportSigningKey:
        return cls(Ed25519KeyPair.from_private_pem(private_key_pem))

    @staticmethod
    def _check_key_permissions(path: Path) -> None:
        try:
            st = os.stat(path)
        except FileNotFoundError as err:
            raise PermissionError(f"Key file not found: {path}") from err
        if st.st_mode & stat.S_IRWXO:
            raise PermissionError(
                f"Private key file {path} is world-readable ({oct(st.st_mode & 0o777)}). "
                "Restrict permissions with: chmod 600"
            )

    @property
    def public_key_pem(self) -> str:
        return self._key.public_key_pem

    @property
    def private_key_pem(self) -> str:
        return self._key.private_key_pem

    @property
    def fingerprint(self) -> str:
        return self._key.fingerprint

    @security_critical
    def sign_report(self, payload: bytes) -> str:
        sig = self._key.sign(payload)
        return base64.b64encode(sig).decode("utf-8")

    @staticmethod
    def verify_signature(public_key_pem: str, signature_b64: str, payload: bytes) -> bool:
        try:
            sig = base64.b64decode(signature_b64)
            return Ed25519KeyPair.verify(public_key_pem, sig, payload)
        except Exception:
            return False

    def save_private_key(self, path: str | Path) -> None:
        key_path = Path(path)
        key_path.write_text(self.private_key_pem, encoding="utf-8")
        key_path.chmod(0o600)

    def save_public_key(self, path: str | Path) -> None:
        Path(path).write_text(self.public_key_pem, encoding="utf-8")

    @classmethod
    def init_key_pair(cls, output_dir: str | Path = ".", encrypt: bool = False) -> ReportSigningKey:
        out = Path(output_dir)
        out.mkdir(parents=True, exist_ok=True)
        key = cls.generate()
        if encrypt:
            key.save_encrypted_private_key(out / f"{_KEY_PURPOSE}.pem")
        else:
            key.save_private_key(out / f"{_KEY_PURPOSE}.pem")
        key.save_public_key(out / f"{_KEY_PURPOSE}.pub")
        (out / "fingerprint.txt").write_text(key.fingerprint + "\n")
        return key
