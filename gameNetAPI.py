import socket
import datetime

# Header details
# TODO maybe checksum
CHANNEL_TYPE_SIZE = 1
SEQ_NUM_SIZE = 2
TIME_STAMP_SIZE = 2
ACK_NUM_SIZE = 2
HEADER_SIZE = CHANNEL_TYPE_SIZE + SEQ_NUM_SIZE + TIME_STAMP_SIZE + ACK_NUM_SIZE

# GO back N parameters for reliable channel
GBN_WINDOW_SIZE = 5
GBN_TIMEOUT = 0.5  # in seconds
BUFFER_SIZE = 50

# unreliable channel parameters
UNRELIABLE_BUFFER_SIZE = 50

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
        header[3:5] = self.time_stamp.to_bytes(2, byteorder='big')
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

class GameNetAPI:
    def __init__(self, local_addr, local_port, remote_addr, remote_port):
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.bind((local_addr, local_port))
        self.remote_addr = remote_addr
        self.remote_port = remote_port

        self.sock.setblocking(False) 
        
        # maybe need to change to local addr
        address = ('localhost', local_port)
        self.sock.bind(('localhost', local_port))

        self.seq_num = 0
        

    def send_packet(self, data, tag):
        if tag == 1:  # reliable channel
            packet = GameNetPacket(channel_type=tag, payload=data, seq_num=self.seq_num, time_stamp=datetime.now(), ack_num=0)
            self.seq_num += 1
        else:  # unreliable channel
            packet = GameNetPacket(channel_type=tag, payload=data, time_stamp=datetime.now())

        self.sock.sendto(packet.to_bytes(), (self.remote_addr, self.remote_port))

    def receive_packet(self) -> GameNetPacket:
        data, _ = self.sock.recvfrom(65535)
        return GameNetPacket.from_bytes(data)

    def close(self):
        self.sock.close()