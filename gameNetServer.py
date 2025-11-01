import socket
import time
import threading
from collections import deque
from gameNetPacket import GameNetPacket

# Selective Repeat parameters for reliable channel
SR_WINDOW_SIZE = 5
BUFFER_SIZE = 1024
MAX_SEQ_NUM = 2 ** 16  # 16-bit sequence numbers
HALF_SEQ_SPACE = MAX_SEQ_NUM // 2  # Window must be ≤ half sequence space
DEFAULT_PORT = 12001
DEFAULT_ADDR = "localhost"

class GameNetServer:
    def __init__(self, addr=DEFAULT_ADDR, port=DEFAULT_PORT, timeout_threshold=0.2, callback_function=None):
        self.socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.socket.bind((addr, port))
        self.socket.setblocking(False)

        # Reliable channel state (Selective Repeat)
        self.reliable_buffer = {}  # {seq_num: packet}
        self.expected_sequence = 0  
        self.first_reliable_packet = True
        self.window_size = SR_WINDOW_SIZE

        # Timeout tracking for missing packets
        self.timeout_threshold = timeout_threshold
        self.waiting_start_time = None
        self.waiting_for_seq = None

        self.client_addr = None
        self.output_buffer = deque()

        self.callback_function = callback_function
        self.receive_thread = None
        self.shutdown_event = threading.Event()
        self.lock = threading.Lock()

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

    def parse_packet(self, data: bytes) -> GameNetPacket:
        return GameNetPacket.from_bytes(data)

    def create_ack_packet(self, sequence_number: int) -> bytes:
        """Build an ACK packet"""
        ack_packet = GameNetPacket(
            channel_type=1, seq_num=0, ack_num=sequence_number)
        return ack_packet.to_bytes()

    def _calculate_latency(self, packet: GameNetPacket) -> float:
        """Calculate one-way latency"""
        if packet.time_stamp > 0:
            return (time.time() - packet.time_stamp) * 1000  # Convert to ms
        return 0

    def _process_socket(self):
        """Internal method to process incoming packets"""
        if self.start_time is None:
            self.start_time = time.time()

        # Check for timeout and skip missing packets
        self._check_timeout()

        # Check if we have buffered data to deliver
        if self.output_buffer:
            payload, channel_type = self.output_buffer.popleft()
            return [payload, channel_type]

        # Try to receive from socket
        try:
            data, self.client_addr = self.socket.recvfrom(BUFFER_SIZE)
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
                f"[UNRELIABLE] SeqNo={packet.seq_num}, Latency={latency:.2f}ms, Payload={packet.payload[:50]}")
            return [packet.payload, packet.channel_type]

        # Reliable channel
        self.metrics["reliable"]["packets_received"] += 1
        self.metrics["reliable"]["bytes_received"] += len(packet.payload)
        if latency > 0:
            self.metrics["reliable"]["latencies"].append(latency)

        # Initialize expected sequence from first reliable packet
        if self.first_reliable_packet:
            self.expected_sequence = packet.seq_num
            self.first_reliable_packet = False
            self._start_waiting(self.expected_sequence)
            print(f"Initialized expected_sequence={self.expected_sequence}")

        # Case 1: Duplicate packet (already delivered, behind window)
        if self._has_been_delivered(packet.seq_num):
            self.metrics["reliable"]["duplicates"] += 1
            print(f"Duplicate SeqNo={packet.seq_num} (Expected={self.expected_sequence}) - Resending ACK")
            self._send_ack(packet.seq_num)

        # Case 2: Packet within receive window [expected_seq, expected_seq + window_size - 1]
        elif self._is_within_receive_window(packet.seq_num):
            if packet.seq_num not in self.reliable_buffer:  # New packet - buffer it
                self.reliable_buffer[packet.seq_num] = packet
                if packet.seq_num != self.expected_sequence:
                    self.metrics["reliable"]["out_of_order"] += 1
                print(
                    f"Buffered SeqNo={packet.seq_num}, Latency={latency:.2f}ms, "
                    f"Expected={self.expected_sequence}, Buffer_size={len(self.reliable_buffer)}"
                )
            else: # Duplicate packet within window
                self.metrics["reliable"]["duplicates"] += 1
                print(f"Duplicate buffered SeqNo={packet.seq_num}")

            # Send ACK 
            self._send_ack(packet.seq_num)

            # Deliver consecutive packets
            self._drain_in_order()

        # Case 3: Packet outside receive window (too ahead or too behind)
        else:
            print(
                f"Out-of-window SeqNo={packet.seq_num}, "
                f"Window=[{self.expected_sequence}, {(self.expected_sequence + self.window_size - 1) % MAX_SEQ_NUM}]"
            )
            # No ACKs for out of window

        # Return data if available after processing
        if self.output_buffer:
            payload, channel_type = self.output_buffer.popleft()
            return [payload, channel_type]

        return None

    def _receive_loop(self):
        """Continuously processes packets"""
        print("[THREAD] Receive thread started")

        while not self.shutdown_event.is_set():
            packet_data = self._process_socket()

            if packet_data and self.callback_function:
                payload, channel_type = packet_data
                self.callback_function(payload, channel_type)

            time.sleep(0.001)  # Sleep to avoid busy-waiting

        print("[THREAD] Receive thread stopped")

    def start(self):
        """Start the receive thread"""
        if self.receive_thread is None or not self.receive_thread.is_alive():
            self.shutdown_event.clear()
            self.receive_thread = threading.Thread(
                target=self._receive_loop, daemon=True)
            self.receive_thread.start()
            print("[SERVER] Started listening for packets")

    def stop(self):
        """Stop the receive thread gracefully"""
        if self.receive_thread and self.receive_thread.is_alive():
            print("[SERVER] Stopping receive thread...")
            self.shutdown_event.set()
            self.receive_thread.join(timeout=2.0)

    def _start_waiting(self, seq_num: int):
        """Start timeout timer for expected sequence number"""
        if self.waiting_for_seq != seq_num:
            self.waiting_for_seq = seq_num
            self.waiting_start_time = time.time()
            print(f"[TIMEOUT] Started waiting for SeqNo={seq_num}")

    def _check_timeout(self):
        """Check if expected packet has timed out and skip if necessary"""
        if self.waiting_start_time is None:
            return

        elapsed = time.time() - self.waiting_start_time

        if (self.waiting_for_seq == self.expected_sequence and elapsed >= self.timeout_threshold):
            self.metrics["reliable"]["timeouts"] += 1
            print(
                f"[TIMEOUT] SeqNo={self.expected_sequence} timed out after {elapsed:.3f}s "
                f"(threshold={self.timeout_threshold}s). Skipping packet..."
            )

            # Skip this packet and slide window forward
            self.expected_sequence = (self.expected_sequence + 1) % MAX_SEQ_NUM

            # Try to deliver buffered consecutive packets
            self._drain_in_order()

            # Update timeout tracking
            if self.expected_sequence in self.reliable_buffer:
                self.waiting_start_time = None
                self.waiting_for_seq = None
            else:
                self._start_waiting(self.expected_sequence)

    def _send_ack(self, seq_num: int):
        """Send ACK for specific sequence number"""
        if self.client_addr is not None:
            ack_pkt = self.create_ack_packet(seq_num)
            self.socket.sendto(ack_pkt, self.client_addr)

    def _drain_in_order(self):
        """Deliver buffered packets in order and slide receive window"""
        delivered_any = False

        while self.expected_sequence in self.reliable_buffer:
            packet = self.reliable_buffer.pop(self.expected_sequence)
            self.output_buffer.append((packet.payload, packet.channel_type))
            print(f"Delivered SeqNo={self.expected_sequence}")
            self.expected_sequence = (self.expected_sequence + 1) % MAX_SEQ_NUM
            delivered_any = True

        # Update timeout
        if delivered_any:
            if self.expected_sequence in self.reliable_buffer:  # Next packet already in output buffer
                self.waiting_start_time = None
                self.waiting_for_seq = None
            else: # Start waiting for new expected sequence
                self._start_waiting(self.expected_sequence)

    def _is_within_receive_window(self, seq_num: int) -> bool:
        """Check if seq_num is within receive window [expected_seq, expected_seq + window_size - 1]"""
        distance_from_window_start = (
            seq_num - self.expected_sequence) % MAX_SEQ_NUM
        return distance_from_window_start < self.window_size

    def _has_been_delivered(self, seq_num: int) -> bool:
        """Check if packet has already been delivered (behind window)"""
        if seq_num == self.expected_sequence:
            return False  

        distance_behind = (self.expected_sequence - seq_num) % MAX_SEQ_NUM
        # Packets 1 to HALF_SEQ_SPACE-1 behind are old (already delivered)
        return 0 < distance_behind < HALF_SEQ_SPACE

    def get_metrics(self):
        """Calculate and return performance metrics"""
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
            },
            "unreliable": {
                "packets_received": self.metrics["unreliable"]["packets_received"],
                "avg_latency_ms": sum(self.metrics["unreliable"]["latencies"]) / len(self.metrics["unreliable"]["latencies"]) if self.metrics["unreliable"]["latencies"] else 0,
                "throughput_bytes": (self.metrics["unreliable"]["bytes_received"]) / duration
            }
        }

        return metrics_report

    def print_metrics(self):
        """Print metrics"""
        metrics = self.get_metrics()

        print(f"Test Duration: {metrics["duration"]:.2f}s\n")

        print("RELIABLE CHANNEL:")
        print(f"Packets Received: {metrics["reliable"]["packets_received"]}")
        print(f"Duplicates: {metrics["reliable"]["duplicates"]}")
        print(f"Out-of-Order: {metrics["reliable"]["out_of_order"]}")
        print(f"Timeouts: {metrics["reliable"]["timeouts"]}")
        print(f"Avg Latency: {metrics["reliable"]["avg_latency_ms"]:.2f} ms")
        print(f"Throughput: {metrics["reliable"]["throughput_bps"]:.2f} bps")
        print(f"Delivery Ratio: {metrics["reliable"]["delivery_ratio_pct"]:.2f}%\n")

        print("UNRELIABLE CHANNEL:")
        print(f"Packets Received: {metrics["unreliable"]["packets_received"]}")
        print(f"Avg Latency: {metrics["unreliable"]["avg_latency_ms"]:.2f} ms")
        print(f"Throughput: {metrics["unreliable"]["throughput_bps"]:.2f} bps")

    def close(self):
        """Clean shutdown of server."""
        self.stop()
        self.socket.close()


if __name__ == "__main__":
    # Callback function that gets called when data is received
    def handle_received_data(payload, channel_type):
        channel_name = "RELIABLE" if channel_type == 1 else "UNRELIABLE"
        print(f"[HELLO FROM RECEIVER APPLICATION] {channel_name}: {payload[:100]}")

    # Create server with callback
    server = GameNetServer(
        addr="localhost",
        port=12001,
        timeout_threshold=0.7,  
        callback_function=handle_received_data
    )

    # Start the internal thread
    server.start()

    try:
        # Main thread can do other work
        print("[APP] Server running. Press Ctrl+C to stop...")
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\n[APP] Shutting down server...")
    finally:
        server.close()
        server.print_metrics()
