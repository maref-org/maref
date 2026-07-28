import os

os.environb[b"MAREF_HMAC_SECRET_KEY"] = b"test-key-insecure-not-for-production"
os.environ["MAREF_HMAC_SECRET_KEY"] = "test-key-insecure-not-for-production"
