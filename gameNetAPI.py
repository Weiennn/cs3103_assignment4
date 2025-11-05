import random
import socket
import time
from gameNetPacket import GameNetPacket
import threading
from collections import deque
import json
import signal
import sys

# Selective Repeat parameters
SR_WINDOW_SIZE = 16
BUFFER_SIZE = 1024
MAX_SEQ_NUM = 2 ** 16  # allow wrap for 16-bit sequence numbers

# Client parameters
RETRANSMISSION_STOP_THRESHOLD = 0.2  # seconds | at which we give up retransmitting
TIMEOUT = 0.05  # seconds | at which we retransmit packets

# Server parameters
HALF_SEQ_SPACE = MAX_SEQ_NUM // 2  # Window must be ≤ half sequence space
DEFAULT_SERVER_ADDR = "localhost"
DEFAULT_SERVER_PORT = 12001

def handle_sigterm(signum, frame):
    print("\nSIGTERM received...")
    sys.exit(0)

signal.signal(signal.SIGTERM, handle_sigterm)

class GameNetAPI:
    def __init__(self, mode, client_addr=None, client_port=None, server_addr=None, server_port=None, timeout=TIMEOUT, callback_function=None):
        self.mode = mode
        self.timeout = timeout
        self.retransmission_stop_threshold = RETRANSMISSION_STOP_THRESHOLD

        self.lock = threading.Lock()

        # Common UDP socket
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.setblocking(False)

        if mode == "server":
            self.client_addr = None
            self.client_port = None
            self.server_addr = server_addr
            self.server_port = server_port
            self.sock.bind((self.server_addr, self.server_port))
            self.callback_function = callback_function
            self._init_server_state()
        elif mode == "client":
            self.client_addr = client_addr
            self.client_port = client_port
            self.server_addr = server_addr
            self.server_port = server_port
            self.sock.bind((self.client_addr, self.client_port))
            self._init_client_state()
        else:
            raise ValueError("Please specify mode as either 'server' or 'client'.")
        
    def _init_client_state(self) -> None:
        '''Client-specific state initialization.'''
        self.seq_num = random.randint(1, MAX_SEQ_NUM)
        self.max_resend_count = RETRANSMISSION_STOP_THRESHOLD // self.timeout

        self.buffer = []  # stores (payload, channel_type)
        self.send_window = {}  # seq -> {packet, timer, resend_count}
        
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

    def _init_server_state(self) -> None:
        '''Server-specific state initialization.'''
        # Reliable channel state (Selective Repeat)
        self.reliable_buffer = {}  # {seq_num: (packet, latency)}
        self.expected_sequence = 0
        self.first_reliable_packet = True
        self.window_size = SR_WINDOW_SIZE

        # Timeout tracking for missing packets
        self.waiting_start_time = None
        self.waiting_for_seq = None

        self.output_buffer = deque()

        self.receive_thread = None
        self.shutdown_event = threading.Event()

        # Performance metrics
        self.total_reliable_sent = 0
        self.total_unreliable_sent = 0
        self.total_reliable_success = 0
        self.metrics = {
            "reliable": {
                "packets_received": 0,
                "duplicates": 0,
                "out_of_order": 0,
                "timeouts": 0,
                "latencies": [],
                "bytes_received": 0
            },
            "unreliable": {
                "packets_received": 0,
                "latencies": [],
                "bytes_received": 0
            }
        }
        self.start_time = None

    # --- Client Methods ---
    def send_packet(self, payload: any, channel_type: int) -> None:
        """Add packet to buffer; notify sender thread if waiting."""
        if self.mode != "client":
            raise RuntimeError("Method cannot be called in client mode.")
        
        if channel_type == 1:
            self.total_reliable_sent += 1
        elif channel_type == 0:
            self.total_unreliable_sent += 1
        with self.condition:
            self.buffer.append((payload, channel_type))
            print(f"[CLIENT] Packet buffered : Channel={channel_type} Payload={payload}")
            self.condition.notify_all()  # wake up window thread if waiting

    # Background thread: move packets from buffer to send window
    def window_packet(self) -> None:
        """ Continuously move packets from buffer to send window when space is available."""
        if self.mode != "client":
            raise RuntimeError("Method cannot be called in client mode.")
        
        while True:
            with self.condition:
                # wait until window not full and buffer not empty
                while len(self.send_window) >= SR_WINDOW_SIZE or len(self.buffer) == 0:
                    print("[CLIENT] Waiting for window...")
                    self.condition.wait()

                payload, channel_type = self.buffer.pop(0)
            
            # send outside the lock to avoid blocking other threads
            self._send_packet_internal(payload, channel_type)

    def _send_packet_internal(self, payload: any, channel_type: int) -> None:
        """Send packet based on channel type."""
        if self.mode != "client":
            raise RuntimeError("Method cannot be called in client mode.")
        
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
            print(f"[CLIENT] Sent reliable packet: Seq={seq}")

            # start timer for retransmission
            timer = threading.Timer(self.timeout, self.retransmit_packet, args=(seq,))
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
            print(f"[CLIENT] Sent session summary: {payload}")
        else:  # Unreliable
            packet = GameNetPacket(
                channel_type=0,
                payload=payload,
                time_stamp=int(time.time() * 1000)
            )
            self.sock.sendto(packet.to_bytes(), (self.server_addr, self.server_port))
            print(f"[CLIENT] Sent unreliable packet: {payload}")

    def retransmit_packet(self, seq: int) -> None:
        """Retransmit packet if ACK not received within timeout. Drop if retransmission threshold reached."""
        if self.mode != "client":
            raise RuntimeError("Method cannot be called in client mode.")
        
        with self.lock:
            entry = self.send_window.get(seq)
            if not entry or self.sock.fileno() == -1:  # socket closed
                return

            if entry["resend_count"] >= self.max_resend_count:
                print(f"[CLIENT] [DROP] Seq={seq} reached max retransmissions.")
                del self.send_window[seq]
                self.condition.notify()  # free window slot
                return

            packet = entry["packet"]
            print(f"[CLIENT] [RETRANSMIT] Seq={seq}")
            self.sock.sendto(packet.to_bytes(), (self.server_addr, self.server_port))
            entry["resend_count"] += 1

            # restart timer
            timer = threading.Timer(self.timeout, self.retransmit_packet, args=(seq,))
            entry["timer"] = timer
            timer.start()

    def receive_acks(self) -> None:
        """ Continuously receive ACKs from server and process them."""
        if self.mode != "client":
            raise RuntimeError("Method cannot be called in client mode.")
        
        while self.running:
            try:
                data, addr = self.sock.recvfrom(4096)
                packet = GameNetPacket.from_bytes(data)

                if packet.channel_type == 1:
                    ack_num = packet.ack_num
                    with self.condition:
                        if ack_num in self.send_window:
                            print(f"[CLIENT] [ACK RECEIVED] Seq={ack_num}")
                            self.send_window[ack_num]["timer"].cancel()
                            del self.send_window[ack_num]
                            # Notify sender thread that window has space now
                            self.condition.notify()
                elif packet.channel_type == 2:
                    print(f"[CLIENT] [SESSION SUMMARY ACK RECEIVED]")
                    self.session_summary_ack.set()
            except BlockingIOError:
                continue

    def close_client(self) -> None:
        """Clean shutdown of client; send session summary to server."""
        if self.mode != "client":
            raise RuntimeError("Method cannot be called in client mode.")

        print("[CLIENT] Closing session...")

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
            if self.session_summary_ack.wait(timeout=TIMEOUT):
                ack_received = True
                break

            print("[CLIENT] Waiting for session summary ACK...")

        self.running = False

        if not ack_received:
            print("[CLIENT] [SESSION CLOSE WARNING] Server did not ACK session summary.")

        with self.lock:
            for seq, entry in list(self.send_window.items()):
                entry["timer"].cancel()

        self.sock.close()
        print("[CLIENT] Shutdown complete.")

    # --- Server Methods ---
    def parse_packet(self, data: bytes) -> GameNetPacket:
        """Parse incoming bytes into GameNetPacket."""
        if self.mode != "server":
            raise RuntimeError("Method can only be called in server mode.")
        
        return GameNetPacket.from_bytes(data)

    def create_ack_packet(self, sequence_number: int) -> bytes:
        """Build an ACK packet using the sequence number received."""
        if self.mode != "server":
            raise RuntimeError("Method can only be called in server mode.")
        
        # ACK the exact packet received
        ack_packet = GameNetPacket(
            channel_type=1, seq_num=0, ack_num=sequence_number)
        # print(f"[SERVER] [ACK CREATED] {ack_packet}")
        return ack_packet.to_bytes()

    def _calculate_latency(self, packet: GameNetPacket) -> float:
        """Calculate one-way latency"""
        if self.mode != "server":
            raise RuntimeError("Method can only be called in server mode.")
        
        if packet.time_stamp > 0:
            # time_stamp given in ms
            return (time.time() * 1000) - packet.time_stamp
        return 0

    def _process_socket(self):
        """Internal method to process incoming packets"""
        if self.mode != "server":
            raise RuntimeError("Method can only be called in server mode.")
    
        if self.start_time is None:
            self.start_time = time.time()

        # Check if we have buffered data to deliver to application
        if self.output_buffer:
            popped_packet, popped_latency = self.output_buffer.popleft()
            self.callback_function(popped_packet, popped_latency)
            return

        # Try to receive from socket
        try:
            data, self.client_addr = self.sock.recvfrom(BUFFER_SIZE)
        except BlockingIOError:
            return None

        packet = self.parse_packet(data)
        latency = self._calculate_latency(packet)

        # Unreliable channel
        if packet.channel_type == 0:
            self.metrics["unreliable"]["packets_received"] += 1
            self.metrics["unreliable"]["bytes_received"] += len(packet.payload)
            if latency > 0:
                self.metrics["unreliable"]["latencies"].append(latency)

            print(
                f"[SERVER] [UNRELIABLE] SeqNo={packet.seq_num}, Latency={latency:.2f}ms, Payload={packet.payload[:50]}")
            self.callback_function(packet, latency)
            return
        
        if packet.channel_type == 2:
            print(f"[SERVER] [SESSION SUMMARY RECEIVED]")
            self._process_session_summary(packet.payload)
            self._send_session_ack()
            return None

        # Reliable channel
        self.metrics["reliable"]["packets_received"] += 1
        self.metrics["reliable"]["bytes_received"] += len(packet.payload)
        if latency > 0:
            self.metrics["reliable"]["latencies"].append(latency)

        # Initialize expected sequence from first reliable packet
        if self.first_reliable_packet:
            self.expected_sequence = packet.seq_num
            self.first_reliable_packet = False
            print(
                f"[SERVER] Initialized expected_sequence={self.expected_sequence}")
            # self._start_waiting(self.expected_sequence)
            

        # Case 1: Duplicate packet (already delivered, behind window)
        if self._has_been_delivered(packet.seq_num):
            self.metrics["reliable"]["duplicates"] += 1
            print(
                f"[SERVER] Duplicate SeqNo={packet.seq_num} (Expected={self.expected_sequence}) - Resending ACK")
            self._send_ack(packet.seq_num)

        # Case 2: Packet within receive window [expected_seq, expected_seq + window_size - 1]
        elif self._is_within_receive_window(packet.seq_num):
            if packet.seq_num not in self.reliable_buffer:  # New packet - buffer it
                self.reliable_buffer[packet.seq_num] = (packet, latency)
                if packet.seq_num != self.expected_sequence:
                    self.metrics["reliable"]["out_of_order"] += 1
                    self._start_waiting(self.expected_sequence)  # Received higher seq, start waiting for expected

                self.total_reliable_success += 1
                print(
                    f"[SERVER] Buffered SeqNo={packet.seq_num}, Latency={latency:.2f}ms, "
                    f"Expected={self.expected_sequence}, Buffer_size={len(self.reliable_buffer)}"
                )
            else:  # Duplicate packet within window
                self.metrics["reliable"]["duplicates"] += 1
                print(f"[SERVER] Duplicate buffered SeqNo={packet.seq_num}")

            # Send ACK
            self._send_ack(packet.seq_num)

            # Deliver consecutive packets
            self._drain_in_order()

        # Case 3: Packet outside receive window (too ahead or too behind)
        else:
            print(
                f"[SERVER] Out-of-window SeqNo={packet.seq_num}, "
                f"Window=[{self.expected_sequence}, {(self.expected_sequence + self.window_size - 1) % MAX_SEQ_NUM}]"
            )
            # No ACKs for out of window

        # Return data if available after processing
        if self.output_buffer:
            popped_packet, popped_latency = self.output_buffer.popleft()
            self.callback_function(popped_packet, popped_latency)
            return
            
        # Check for timeout and skip missing packets
        self._check_timeout()

        return None

    def _receive_loop(self):
        """Continuously processes packets"""
        if self.mode != "server":
            raise RuntimeError("Method can only be called in server mode.")

        print("[SERVER] [THREAD] Receive thread started")

        while not self.shutdown_event.is_set():
            self._process_socket()
            time.sleep(0.001)  # Sleep to avoid busy-waiting

        print("[SERVER] [THREAD] Receive thread stopped")

    def start(self):
        """Start the receive thread"""
        if self.mode != "server":
            raise RuntimeError("Method can only be called in server mode.")
        
        if self.receive_thread is None or not self.receive_thread.is_alive():
            self.shutdown_event.clear()
            self.receive_thread = threading.Thread(
                target=self._receive_loop, daemon=True)
            self.receive_thread.start()
            print("[SERVER] Started listening for packets")

    def stop(self):
        """Stop the receive thread gracefully"""
        if self.mode != "server":
            raise RuntimeError("Method can only be called in server mode.")
        
        if self.receive_thread and self.receive_thread.is_alive():
            print("[SERVER] Stopping receive thread due to stop method given...")
            self.shutdown_event.set()
            self.receive_thread.join()

    def _start_waiting(self, seq_num: int):
        """Start timeout timer for expected sequence number"""
        if self.mode != "server":
            raise RuntimeError("Method can only be called in server mode.")
        
        if self.waiting_for_seq != seq_num:
            self.waiting_for_seq = seq_num
            self.waiting_start_time = time.time()
            print(f"[SERVER] Started waiting for SeqNo={seq_num}")

    def _check_timeout(self):
        """Check if expected packet has timed out and skip if necessary"""
        if self.mode != "server":
            raise RuntimeError("Method can only be called in server mode.")
        
        if self.waiting_start_time is None:
            return

        elapsed = time.time() - self.waiting_start_time

        if (self.waiting_for_seq == self.expected_sequence and elapsed >= self.retransmission_stop_threshold):
            self.metrics["reliable"]["timeouts"] += 1
            print(
                f"[SERVER] [TIMEOUT] SeqNo={self.expected_sequence} timed out after {elapsed:.3f}s "
                f"(threshold={self.retransmission_stop_threshold}s). Skipping packet..."
            )

            if len(self.reliable_buffer) == 0:  # Empty buffer, return
                return

            # Try to deliver buffered least consecutive packets
            min_seq = min(self.reliable_buffer.keys())
            while min_seq in self.reliable_buffer:
                packet, latency = self.reliable_buffer.pop(min_seq)
                print(
                    f"[SERVER] Delivering SeqNo={min_seq} to receiver application")
                self.output_buffer.append((packet, latency))
                min_seq = (min_seq + 1) % MAX_SEQ_NUM
                self.expected_sequence = min_seq

            # Update timeout tracking
            self.waiting_start_time = None # Reset timeout until next higher seq packet arrives
            self.waiting_for_seq = None

    # For reliable packets
    def _send_ack(self, seq_num: int):
        """Send ACK for specific sequence number"""
        if self.mode != "server":
            raise RuntimeError("Method can only be called in server mode.")
        
        if self.client_addr is not None:
            print(f"[SERVER] [ACK SENT] SeqNo={seq_num}")
            ack_pkt = self.create_ack_packet(seq_num)
            self.sock.sendto(ack_pkt, self.client_addr)

    def _send_session_ack(self):
        """Send ACK for session summary"""
        if self.mode != "server":
            raise RuntimeError("Method can only be called in server mode.")
        
        if self.client_addr is not None:
            ack_packet = GameNetPacket(channel_type=2, seq_num=0, ack_num=0)
            print(f"[SERVER] [SESSION SUMMARY ACK SENT]")
            self.sock.sendto(ack_packet.to_bytes(), self.client_addr)

    def _drain_in_order(self):
        """Deliver buffered packets in order and slide receive window"""
        if self.mode != "server":
            raise RuntimeError("Method can only be called in server mode.")
        
        if len(self.reliable_buffer) == 0: # Empty buffer, return
            return

        # Else deliver consecutive packets
        while self.expected_sequence in self.reliable_buffer:
            packet, latency = self.reliable_buffer.pop(self.expected_sequence)
            self.output_buffer.append((packet, latency))
            print(f"[SERVER] Delivered SeqNo={self.expected_sequence}")
            self.expected_sequence = (self.expected_sequence + 1) % MAX_SEQ_NUM

    def _is_within_receive_window(self, seq_num: int) -> bool:
        """Check if seq_num is within receive window [expected_seq, expected_seq + window_size - 1]"""
        if self.mode != "server":
            raise RuntimeError("Method can only be called in server mode.")
        
        distance_from_window_start = (
            seq_num - self.expected_sequence) % MAX_SEQ_NUM
        return distance_from_window_start < self.window_size

    def _has_been_delivered(self, seq_num: int) -> bool:
        """Check if packet has already been delivered (behind window)"""
        if self.mode != "server":
            raise RuntimeError("Method can only be called in server mode.")
        
        if seq_num == self.expected_sequence:
            return False

        distance_behind = (self.expected_sequence - seq_num) % MAX_SEQ_NUM
        # Packets 1 to HALF_SEQ_SPACE-1 behind are old (already delivered)
        return 0 < distance_behind < HALF_SEQ_SPACE
    
    def _process_session_summary(self, payload: bytes):
        """Process session summary received from client"""
        if self.mode != "server":
            raise RuntimeError("Method can only be called in server mode.")
        
        try:
            summary = json.loads(payload.decode())
            self.total_reliable_sent = summary.get("total_reliable_sent", 0)
            self.total_unreliable_sent = summary.get("total_unreliable_sent", 0)
            print(f"[SERVER] [SESSION SUMMARY] Reliable Sent={self.total_reliable_sent}, Unreliable Sent={self.total_unreliable_sent}")

        except Exception as e:
            print(f"[SERVER] [ERROR] Failed to process session summary: {e}")

    def _calculate_jitter(self, latencies):
        """Calculate jitter following RFC 3550 standard"""
        if self.mode != "server":
            raise RuntimeError("Method can only be called in server mode.")
        
        if len(latencies) < 2:
            return 0

        jitter = 0

        for i in range(1, len(latencies)):
            # Difference between consecutive latencies
            transit_diff = abs(latencies[i] - latencies[i-1])

            # s->jitter += (1./16.) * ((double)d - s->jitter)
            jitter = jitter + (transit_diff - jitter) / 16

        return jitter

    def get_metrics(self):
        """Calculate and return performance metrics"""
        if self.mode != "server":
            raise RuntimeError("Method can only be called in server mode.")
        
        duration = time.time() - self.start_time if self.start_time else 1

        metrics_report = {
            "duration": duration,
            "reliable": {
                "packets_received": self.metrics["reliable"]["packets_received"],
                "duplicates": self.metrics["reliable"]["duplicates"],
                "out_of_order": self.metrics["reliable"]["out_of_order"],
                "timeouts": self.metrics["reliable"]["timeouts"],
                "avg_latency_ms": sum(self.metrics["reliable"]["latencies"]) / len(self.metrics["reliable"]["latencies"]) if self.metrics["reliable"]["latencies"] else 0,
                "throughput_bytes": (self.metrics["reliable"]["bytes_received"]) / duration,
                "delivery_ratio_pct": self.total_reliable_success / self.total_reliable_sent * 100 if self.total_reliable_sent > 0 else 0,
                "jitter_ms": self._calculate_jitter(self.metrics["reliable"]["latencies"])
            },
            "unreliable": {
                "packets_received": self.metrics["unreliable"]["packets_received"],
                "avg_latency_ms": sum(self.metrics["unreliable"]["latencies"]) / len(self.metrics["unreliable"]["latencies"]) if self.metrics["unreliable"]["latencies"] else 0,
                "throughput_bytes": (self.metrics["unreliable"]["bytes_received"]) / duration,
                "delivery_ratio_pct": self.metrics["unreliable"]["packets_received"] / self.total_unreliable_sent * 100 if self.total_unreliable_sent > 0 else 0,
                "jitter_ms": self._calculate_jitter(self.metrics["unreliable"]["latencies"])
            }
        }

        return metrics_report

    def print_metrics(self):
        """Print metrics"""
        if self.mode != "server":
            raise RuntimeError("Method can only be called in server mode.")
        
        metrics = self.get_metrics()

        print(f"Test Duration: {metrics["duration"]:.2f}s\n")

        print("RELIABLE CHANNEL:")
        # print(f"Packets Received: {metrics["reliable"]["packets_received"]}")
        # print(f"Duplicates: {metrics["reliable"]["duplicates"]}")
        # print(f"Out-of-Order: {metrics["reliable"]["out_of_order"]}")
        # print(f"Timeouts: {metrics["reliable"]["timeouts"]}")
        print(f"Avg Latency: {metrics["reliable"]["avg_latency_ms"]:.2f} ms")
        print(f"Throughput: {metrics["reliable"]["throughput_bytes"]:.2f} bps")
        print(f"Delivery Ratio: {metrics["reliable"]["delivery_ratio_pct"]:.2f}%")
        print(f"Jitter: {metrics["reliable"]["jitter_ms"]:.2f} ms\n")

        print("UNRELIABLE CHANNEL:")
        # print(f"Packets Received: {metrics["unreliable"]["packets_received"]}")
        print(f"Avg Latency: {metrics["unreliable"]["avg_latency_ms"]:.2f} ms")
        print(f"Throughput: {metrics["unreliable"]["throughput_bytes"]:.2f} bps")
        print(f"Delivery Ratio: {metrics["unreliable"]["delivery_ratio_pct"]:.2f}%")
        print(f"Jitter: {metrics["unreliable"]["jitter_ms"]:.2f} ms")

    def close_server(self):
        """Clean shutdown of server."""
        if self.mode != "server":
            raise RuntimeError("Method can only be called in server mode.")
        
        self.stop()
        self.sock.close()
        self.print_metrics()
        print("[SERVER] Shutdown complete.")