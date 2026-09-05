import os
import sys

_generated_dir = os.path.dirname(os.path.abspath(__file__))
if _generated_dir not in sys.path:
    sys.path.insert(0, _generated_dir)

import voiceshield_pb2
import voiceshield_pb2_grpc

__all__ = ["voiceshield_pb2", "voiceshield_pb2_grpc"]
