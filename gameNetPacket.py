from datetime import datetime

CHANNEL_TYPE_SIZE = 1
SEQ_NUM_SIZE = 2
ACK_NUM_SIZE = 2
TIME_STAMP_SIZE = 4
HEADER_SIZE = CHANNEL_TYPE_SIZE + SEQ_NUM_SIZE + TIME_STAMP_SIZE + ACK_NUM_SIZE

class GameNetPacket:
    def __init__(self, channel_type=0, seq_num=0, time_stamp=int(datetime.now().timestamp()), ack_num=0, payload=b''):
        self.channel_type = channel_type
        self.seq_num = seq_num
        self.time_stamp = time_stamp
        self.ack_num = ack_num
        self.payload = payload

    def to_bytes(self):
        header = bytearray(HEADER_SIZE)
        header[0] = self.channel_type
        header[1:3] = self.seq_num.to_bytes(2, byteorder='big')
        header[3:7] = self.time_stamp.to_bytes(4, byteorder='big')
        header[7:9] = self.ack_num.to_bytes(2, byteorder='big')
        return bytes(header) + self.payload

    @classmethod
    def from_bytes(cls, data):
        if len(data) < HEADER_SIZE:
            raise ValueError("Data is too short to contain a valid header")
        channel_type = data[0]
        seq_num = int.from_bytes(data[1:3], byteorder='big')
        time_stamp = int.from_bytes(data[3:7], byteorder='big')
        ack_num = int.from_bytes(data[7:9], byteorder='big')
        payload = data[HEADER_SIZE:]
        return cls(channel_type, seq_num, time_stamp, ack_num, payload)

    def __repr__(self):
        return (f"GameNetPacket(channel_type={self.channel_type}, "
                f"seq_num={self.seq_num}, time_stamp={self.time_stamp}, "
                f"ack_num={self.ack_num}, payload_length={len(self.payload)})")
