from __future__ import annotations

from google.protobuf.message import DecodeError

from pyglaze.mimlink.framing import FrameDecodeError, decode_frame, encode_frame
from pyglaze.mimlink.proto.envelope_pb2 import Envelope


class EnvelopeCodec:
    """Stateless codec that converts Envelopes to/from framed wire bytes.

    Manages TX sequence numbering. All message construction is the caller's
    responsibility — this class only handles serialization and framing.
    """

    def __init__(self) -> None:
        self._tx_seq = 0

    def _new_envelope(self) -> Envelope:
        return Envelope()

    def build_envelope(self, env_type: int) -> Envelope:
        """Create an Envelope with seq and type pre-filled."""
        env = self._new_envelope()
        env.seq = self._tx_seq
        env.type = env_type
        return env

    def encode(self, envelope: Envelope) -> bytes:
        """Serialize an Envelope to framed wire bytes."""
        envelope.seq = self._tx_seq
        self._tx_seq = (self._tx_seq + 1) & 0xFFFFFFFF
        return encode_frame(envelope.SerializeToString())

    def decode(self, frame: bytes) -> Envelope:
        """Decode framed wire bytes into an Envelope. Raises on CRC/parse error."""
        payload = decode_frame(frame)
        env = self._new_envelope()
        try:
            env.ParseFromString(payload)
        except DecodeError as e:
            msg = f"Failed to parse protobuf: {e}"
            raise FrameDecodeError(msg) from e
        return env
