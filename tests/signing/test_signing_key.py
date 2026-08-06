from __future__ import annotations

import os
import stat
import tempfile

import pytest

from maref.signing.signing_key import ReportSigningKey


class TestReportSigningKey:
    def test_generate(self) -> None:
        key = ReportSigningKey.generate()
        assert key.private_key_pem.startswith("-----BEGIN PRIVATE KEY-----")
        assert key.public_key_pem.startswith("-----BEGIN PUBLIC KEY-----")
        assert len(key.fingerprint) == 16  # matches Ed25519KeyPair

    def test_fingerprint_stable(self) -> None:
        key = ReportSigningKey.generate()
        fp1 = key.fingerprint
        fp2 = key.fingerprint
        assert fp1 == fp2

    def test_sign_and_verify(self) -> None:
        key = ReportSigningKey.generate()
        payload = b"test governance report payload"
        sig = key.sign_report(payload)
        assert isinstance(sig, str)
        assert ReportSigningKey.verify_signature(
            key.public_key_pem, sig, payload
        ) is True

    def test_verify_tampered_payload(self) -> None:
        key = ReportSigningKey.generate()
        payload = b"original payload"
        sig = key.sign_report(payload)
        assert (
            ReportSigningKey.verify_signature(
                key.public_key_pem, sig, b"tampered payload"
            )
            is False
        )

    def test_verify_invalid_signature(self) -> None:
        key = ReportSigningKey.generate()
        assert (
            ReportSigningKey.verify_signature(
                key.public_key_pem, "invalid_base64!!", b"payload"
            )
            is False
        )

    def test_from_private_pem_roundtrip(self) -> None:
        key1 = ReportSigningKey.generate()
        pem = key1.private_key_pem
        key2 = ReportSigningKey.from_private_pem(pem)
        assert key2.public_key_pem == key1.public_key_pem
        assert key2.fingerprint == key1.fingerprint

    def test_from_private_key_file(self) -> None:
        key1 = ReportSigningKey.generate()
        with tempfile.NamedTemporaryFile(mode="w", suffix=".pem", delete=False) as f:
            f.write(key1.private_key_pem)
            tmp_path = f.name
        os.chmod(tmp_path, 0o600)
        try:
            key2 = ReportSigningKey.from_private_key_file(tmp_path)
            assert key2.fingerprint == key1.fingerprint
        finally:
            os.unlink(tmp_path)

    def test_world_readable_key_rejected(self) -> None:
        key1 = ReportSigningKey.generate()
        with tempfile.NamedTemporaryFile(mode="w", suffix=".pem", delete=False) as f:
            f.write(key1.private_key_pem)
            tmp_path = f.name
        os.chmod(tmp_path, 0o644)
        try:
            with pytest.raises(PermissionError, match="world-readable"):
                ReportSigningKey.from_private_key_file(tmp_path)
        finally:
            os.unlink(tmp_path)

    def test_init_key_pair_creates_files(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            key = ReportSigningKey.init_key_pair(tmpdir)
            assert os.path.exists(os.path.join(tmpdir, "maref-report-signing.pem"))
            assert os.path.exists(os.path.join(tmpdir, "maref-report-signing.pub"))
            assert os.path.exists(os.path.join(tmpdir, "fingerprint.txt"))
            with open(os.path.join(tmpdir, "fingerprint.txt")) as f:
                fp_file = f.read().strip()
            assert fp_file == key.fingerprint
            priv_st = os.stat(os.path.join(tmpdir, "maref-report-signing.pem"))
            assert not priv_st.st_mode & stat.S_IRWXO

    def test_save_private_key_permissions(self) -> None:
        key = ReportSigningKey.generate()
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "test_key.pem")
            key.save_private_key(path)
            st = os.stat(path)
            assert not st.st_mode & stat.S_IRWXO

    def test_different_keys_have_different_fingerprints(self) -> None:
        k1 = ReportSigningKey.generate()
        k2 = ReportSigningKey.generate()
        assert k1.fingerprint != k2.fingerprint
