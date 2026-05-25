"""国密库 PoC 验证脚本 — gmssl 选型测试.

验证范围：SM2 加解密/签名、SM3 哈希、SM4 CBC 加解密
"""
from __future__ import annotations

import sys
from gmssl import sm2, sm3, sm4, func


SM2_PRIVATE_KEY = (
    "00B9AB0B828FF68872F21A837FC303668428DEA11DCD1B24429D0C99E24EED83D5"
)
SM2_PUBLIC_KEY = (
    "B9C9A6E04E9C91F7BA880429273747D7EF5DDEB0BB2FF6317EB00BEF331A83081A6994B8993F3F5D6EADDDB81872266C87C018FB4162F5AF347B483E24620207"
)
SM4_KEY = b"3l5butlj26hvv313"
SM4_IV = b"\x00" * 16


def test_sm3() -> bool:
    """SM3 哈希算法验证."""
    print("=== SM3 ===")
    result = sm3.sm3_hash(list(b"abc"))
    expected = "66c7f0f462eeedd9d1f2d46bdc10e4e24167c4875cf2f7a2297da02b8f4ba8e0"
    ok = result == expected
    print(f"  result:   {result}")
    print(f"  expected: {expected}")
    print(f"  PASS: {ok}")
    return ok


def test_sm4() -> bool:
    """SM4 CBC 加解密验证."""
    print("\n=== SM4 CBC ===")
    value = b"hello sm4"
    crypt_sm4 = sm4.CryptSM4(padding_mode=3)
    crypt_sm4.set_key(SM4_KEY, sm4.SM4_ENCRYPT)
    enc = crypt_sm4.crypt_cbc(SM4_IV, value)
    crypt_sm4.set_key(SM4_KEY, sm4.SM4_DECRYPT)
    dec = crypt_sm4.crypt_cbc(SM4_IV, enc)
    ok = dec == value
    print(f"  plaintext:  {value}")
    print(f"  decrypted:  {dec}")
    print(f"  PASS: {ok}")
    return ok


def test_sm2_encrypt() -> bool:
    """SM2 加解密验证."""
    print("\n=== SM2 Encrypt ===")
    sm2_crypt = sm2.CryptSM2(
        public_key=SM2_PUBLIC_KEY, private_key=SM2_PRIVATE_KEY
    )
    data = b"test"
    enc_data = sm2_crypt.encrypt(data)
    dec_data = sm2_crypt.decrypt(enc_data)
    ok = dec_data == data
    print(f"  plaintext:  {data}")
    print(f"  decrypted:  {dec_data}")
    print(f"  PASS: {ok}")
    return ok


def test_sm2_sign() -> bool:
    """SM2 签名验证."""
    print("\n=== SM2 Sign ===")
    sm2_crypt = sm2.CryptSM2(
        public_key=SM2_PUBLIC_KEY, private_key=SM2_PRIVATE_KEY
    )
    data = b"test"
    random_hex = func.random_hex(sm2_crypt.para_len)
    sign = sm2_crypt.sign(data, random_hex)
    ok = sm2_crypt.verify(sign, data)
    print(f"  data:   {data}")
    print(f"  sign:   {sign[:32]}...")
    print(f"  verify: {ok}")
    return ok


def test_sm2_sign_with_sm3() -> bool:
    """SM2 with SM3 签名验证（推荐，无需外部随机数）."""
    print("\n=== SM2 Sign with SM3 ===")
    sm2_crypt = sm2.CryptSM2(
        public_key=SM2_PUBLIC_KEY, private_key=SM2_PRIVATE_KEY
    )
    data = b"test"
    sign = sm2_crypt.sign_with_sm3(data)
    ok = sm2_crypt.verify_with_sm3(sign, data)
    print(f"  data:   {data}")
    print(f"  sign:   {sign[:32]}...")
    print(f"  verify: {ok}")
    return ok


def main() -> int:
    results = [
        test_sm3(),
        test_sm4(),
        test_sm2_encrypt(),
        test_sm2_sign(),
        test_sm2_sign_with_sm3(),
    ]
    print("\n" + "=" * 40)
    print(f"Results: {sum(results)}/{len(results)} passed")
    return 0 if all(results) else 1


if __name__ == "__main__":
    sys.exit(main())
