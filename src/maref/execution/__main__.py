"""启动 Harness 服务的入口点。"""

from maref.execution.server import start

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="MAREF Harness Service")
    parser.add_argument("--host", default="0.0.0.0", help="Bind address")
    parser.add_argument("--port", type=int, default=8000, help="Bind port")
    args = parser.parse_args()
    start(host=args.host, port=args.port)
