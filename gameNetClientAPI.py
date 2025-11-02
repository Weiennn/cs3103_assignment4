import json
import socket
import random
import threading
from gameNetPacket import GameNetPacket
import time

# Selective Repeat parameters
SR_WINDOW_SIZE = 5
BUFFER_SIZE = 1024
MAX_SEQ_NUM = 2 ** 16  # allow wrap for 16-bit sequence numbers
RETRANSMISSION_THRESHOLD = 200  # ms
TIMEOUT = 50  # ms

class GameNetClientAPI:
    def __init__(self, client_addr, client_port, server_addr, server_port, timeout=TIMEOUT):
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.bind((client_addr, client_port))
        self.sock.setblocking(False)

        self.server_addr = server_addr
        self.server_port = server_port

        self.seq_num = random.randint(1, MAX_SEQ_NUM)
        self.timeout_ms = timeout  # in ms
        self.max_resend_count = RETRANSMISSION_THRESHOLD // self.timeout_ms

        self.buffer = []  # stores (payload, channel_type)
        self.send_window = {}  # seq -> {packet, timer, resend_count}

        self.lock = threading.Lock()
        self.condition = threading.Condition(self.lock)

        # For performance metrics
        self.total_reliable_sent = 0
        self.total_unreliable_sent = 0

        # session closing flags
        self.session_summary_ack = threading.Event()
        self.running = True

        # background threads
        threading.Thread(target=self.receive_acks, daemon=True).start()
        threading.Thread(target=self.window_packet, daemon=True).start()

    def send_packet(self, payload: any, channel_type: int) -> None:
        """Add packet to buffer; notify sender thread if waiting."""
        if channel_type == 1:
            self.total_reliable_sent += 1
        elif channel_type == 0:
            self.total_unreliable_sent += 1
        with self.condition:
            self.buffer.append((payload, channel_type))
            print(f"[BUFFERED] Channel={channel_type} Payload={payload}")
            self.condition.notify_all()  # wake up window thread if waiting

    # Background thread: move packets from buffer to send window
    def window_packet(self) -> None:
        """ Continuously move packets from buffer to send window when space is available."""
        while True:
            with self.condition:
                # wait until window not full and buffer not empty
                while len(self.send_window) >= SR_WINDOW_SIZE or len(self.buffer) == 0:
                    print("[WAITING FOR WINDOW...]")
                    self.condition.wait()

                payload, channel_type = self.buffer.pop(0)
            
            # send outside the lock to avoid blocking other threads
            self._send_packet_internal(payload, channel_type)

    def _send_packet_internal(self, payload: any, channel_type: int) -> None:
        """Send packet based on channel type."""
        if channel_type == 1:  # Reliable
            with self.lock:
                seq = self.seq_num
                packet = GameNetPacket(
                    channel_type=1,
                    payload=payload,
                    seq_num=seq,
                    time_stamp=int(time.time() * 1000)
                )

                self.send_window[seq] = {
                    "packet": packet,
                    "timer": None,
                    "resend_count": 0
                }
                self.seq_num = (self.seq_num + 1) % MAX_SEQ_NUM

            self.sock.sendto(packet.to_bytes(), (self.server_addr, self.server_port))
            print(f"[SEND-RELIABLE] Seq={seq}")

            # start timer for retransmission
            timer = threading.Timer(self.timeout_ms / 1000, self.retransmit_packet, args=(seq,))
            with self.lock:
                if seq in self.send_window:
                    self.send_window[seq]["timer"] = timer
            timer.start()
        elif channel_type == 2:  # Session Summary
            packet = GameNetPacket(
                channel_type=2,
                payload=payload,
                time_stamp=int(time.time() * 1000)
            )
            self.sock.sendto(packet.to_bytes(), (self.server_addr, self.server_port))
            print(f"[SEND-SESSION-SUMMARY] {payload}")
        else:  # Unreliable
            packet = GameNetPacket(
                channel_type=0,
                payload=payload,
                time_stamp=int(time.time() * 1000)
            )
            self.sock.sendto(packet.to_bytes(), (self.server_addr, self.server_port))
            print(f"[SEND-UNRELIABLE] {payload}")

    def retransmit_packet(self, seq: int) -> None:
        """Retransmit packet if ACK not received within timeout. Drop if retransmission threshold reached."""
        with self.lock:
            entry = self.send_window.get(seq)
            if not entry or self.sock.fileno() == -1:  # socket closed
                return

            if entry["resend_count"] >= self.max_resend_count:
                print(f"[DROP] Seq={seq} reached max retransmissions.")
                del self.send_window[seq]
                self.condition.notify()  # free window slot
                return

            packet = entry["packet"]
            print(f"[RETRANSMIT] Seq={seq}")
            self.sock.sendto(packet.to_bytes(), (self.server_addr, self.server_port))
            entry["resend_count"] += 1

            # restart timer
            timer = threading.Timer(self.timeout_ms / 1000, self.retransmit_packet, args=(seq,))
            entry["timer"] = timer
            timer.start()

    def receive_acks(self) -> None:
        """ Continuously receive ACKs from server and process them."""
        while self.running:
            try:
                data, addr = self.sock.recvfrom(4096)
                packet = GameNetPacket.from_bytes(data)

                if packet.channel_type == 1:
                    ack_num = packet.ack_num
                    with self.condition:
                        if ack_num in self.send_window:
                            print(f"[ACK RECEIVED] Seq={ack_num}")
                            self.send_window[ack_num]["timer"].cancel()
                            del self.send_window[ack_num]
                            # Notify sender thread that window has space now
                            self.condition.notify()
                elif packet.channel_type == 2:
                    print(f"[SESSION SUMMARY ACK RECEIVED]")
                    self.session_summary_ack.set()
            except BlockingIOError:
                continue

    def close(self) -> None:
        """Clean shutdown of client; send session summary to server."""
        print("[CLOSING SESSION...]")

        # Send session summary (total packets sent)
        summary = {
            "type": "SESSION_END",
            "total_reliable_sent": self.total_reliable_sent,
            "total_unreliable_sent": self.total_unreliable_sent,
        }

        payload = json.dumps(summary).encode()
        retries = 3 # number of retries for session summary ack
        ack_received = False

        for attempt in range(retries):
            self._send_packet_internal(payload, 2)

            # wait for ack
            if self.session_summary_ack.wait(timeout=TIMEOUT / 1000):
                ack_received = True
                break

            print("[WAITING FOR SESSION SUMMARY ACK...] Retrying...")

        self.running = False

        if not ack_received:
            print("[SESSION CLOSE WARNING] Server did not ACK session summary.")

        with self.lock:
            for seq, entry in list(self.send_window.items()):
                entry["timer"].cancel()

        self.sock.close()
        print("[SESSION CLOSED COMPLETE]")

if __name__ == "__main__":
    client = GameNetClientAPI('localhost', 12345, 'localhost', 12001)

    client.send_packet(b'Hello Reliable 1', 1)
    client.send_packet(b'Hello Unreliable', 0)
    client.send_packet(b'Hello Reliable 2', 1)

    time.sleep(5)  # wait for packets to be sent and acks to be received
    client.close()
