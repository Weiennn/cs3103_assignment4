import socket
import random
import datetime

# Header details
CHANNEL_TYPE_SIZE = 1
SEQ_NUM_SIZE = 2
ACK_NUM_SIZE = 2
TIME_STAMP_SIZE = 4
HEADER_SIZE = CHANNEL_TYPE_SIZE + SEQ_NUM_SIZE + TIME_STAMP_SIZE + ACK_NUM_SIZE

class GameNetPacket:
    def __init__(self, channel_type=0, seq_num=0, time_stamp=0, ack_num=0, payload=b''):
        self.channel_type = channel_type
        self.seq_num = seq_num
        self.time_stamp = time_stamp
        self.ack_num = ack_num
        self.payload = payload

    def to_bytes(self):
        header = bytearray(HEADER_SIZE)
        header[0] = self.channel_type
        header[1:3] = self.seq_num.to_bytes(2, byteorder='big')
        header[3:5] = self.time_stamp.to_bytes(4, byteorder='big')
        header[5:7] = self.ack_num.to_bytes(2, byteorder='big')
        return bytes(header) + self.payload

    @classmethod
    def from_bytes(cls, data):
        if len(data) < HEADER_SIZE:
            raise ValueError("Data is too short to contain a valid header")
        channel_type = data[0]
        seq_num = int.from_bytes(data[1:3], byteorder='big')
        time_stamp = int.from_bytes(data[3:5], byteorder='big')
        ack_num = int.from_bytes(data[5:7], byteorder='big')
        payload = data[HEADER_SIZE:]
        return cls(channel_type, seq_num, time_stamp, ack_num, payload)
    
    def __repr__(self):
        return (f"GameNetPacket(channel_type={self.channel_type}, "
                f"seq_num={self.seq_num}, time_stamp={self.time_stamp}, "
                f"ack_num={self.ack_num}, payload_length={len(self.payload)})")
    
class GameNetClientAPI:
    def __init__(self, client_addr, client_port):
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.bind((client_addr, client_port))
        self.seq_num = random.randint(1, 65535)

    def send_packet(self, server_addr, server_port, payload, tag):
        if tag == 1:  # reliable channel
            packet = GameNetPacket(channel_type=1, payload=payload, seq_num=self.seq_num, time_stamp=int(datetime.datetime.now().timestamp()))
            self.seq_num = (self.seq_num + 1) % 65536
        else:  # unreliable channel
            packet = GameNetPacket(channel_type=0, payload=payload, time_stamp=int(datetime.datetime.now().timestamp()))

        self.sock.sendto(packet.to_bytes(), (server_addr, server_port))
        print(f"Sent: {packet}")

if __name__ == "__main__":
    client = GameNetClientAPI('localhost', 12345)
    client.send_packet('localhost', 54321, b'Hello, Game Server!', tag=1)
    client.send_packet('localhost', 54321, b'Hello, Game Server!', tag=0)

