import socket
import datetime
from gameNetPacket import GameNetPacket
from datetime import datetime

# GO back N parameters for reliable channel
GBN_WINDOW_SIZE = 5
GBN_TIMEOUT = 0.5  # in seconds
BUFFER_SIZE = 50

# unreliable channel parameters
UNRELIABLE_BUFFER_SIZE = 50

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