"""
VoiceShield AI — gRPC Server Runner
Starts the standalone gRPC server for enterprise banking & contact center integration.
"""

import os
import sys
import time

# Ensure project root is in python path
_project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

from grpc_server.servicer import create_grpc_server


def serve():
    port = int(os.getenv("GRPC_PORT", "50051"))
    server = create_grpc_server(port=port)
    server.start()
    print(f"[VoiceShield:gRPC] High-performance gRPC Server listening on port {port}")
    try:
        while True:
            time.sleep(86400)
    except KeyboardInterrupt:
        print("[VoiceShield:gRPC] Shutting down gRPC Server...")
        server.stop(0)


if __name__ == "__main__":
    serve()
