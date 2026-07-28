import os

os.environb[b"MAREF_HMAC_SECRET_KEY"] = b"test-key-insecure-not-for-production"
os.environ["MAREF_HMAC_SECRET_KEY"] = "test-key-insecure-not-for-production"
os.environb[b"MAREF_BFT_SECRET_KEY"] = b"test-bft-key-insecure-not-for-production"
os.environ["MAREF_BFT_SECRET_KEY"] = "test-bft-key-insecure-not-for-production"
os.environb[b"MAREF_MCP_SECRET_KEY"] = b"test-mcp-key-insecure-not-for-production"
os.environ["MAREF_MCP_SECRET_KEY"] = "test-mcp-key-insecure-not-for-production"
os.environ["MAREF_BROWSER_AUTH_KEY"] = "test-browser-auth-key-insecure-not-for-production"
