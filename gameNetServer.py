import socket
import time
from collections import deque
from gameNetAPI import GameNetPacket

# Selective Repeat parameters for reliable channel
SR_WINDOW_SIZE = 5
BUFFER_SIZE = 1024
MAX_SEQ_NUM = 2 ** 16  # allow wrap for 16-bit sequence numbers
HALF_SEQ_SPACE = MAX_SEQ_NUM // 2  # half the sequence space so theres no repeats within window
DEFAULT_PORT = 12001
DEFAULT_ADDR = 'localhost'

class GameNetServer:
    def __init__(self, addr=DEFAULT_ADDR, port=DEFAULT_PORT, timeout_threshold=0.2):
        self.socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.socket.bind((addr, port))
        self.socket.setblocking(False)

        # Reliable channel state
        self.reliable_buffer = {}  # {seq_num: packet}
        self.expected_sequence = 0
        self.first_reliable_packet = True
        self.window_size = SR_WINDOW_SIZE

        # Timeout tracking
        self.timeout_threshold = timeout_threshold
        self.waiting_start_time = None  # when we started waiting for expected_sequence
        self.waiting_for_seq = None  # which sequence number we're waiting for

        self.client_addr = None
        self.output_buffer = deque()

    def parse_packet(self, data: bytes) -> GameNetPacket:
        return GameNetPacket.from_bytes(data)

    def create_ack_packet(self, sequence_number: int) -> bytes:
        """Build an ACK packet using the sequence number received."""
        # ACK the exact packet received
        ack_packet = GameNetPacket(channel_type=1, seq_num=0, ack_num=sequence_number)
        return ack_packet.to_bytes()

    def get_data(self):
        """Return the next payload if available, otherwise process socket input."""
        # Check for timeout and skip missing packets
        self._check_timeout()

        # Buffer is not empty, return next payload
        if self.output_buffer:
            payload, channel_type = self.output_buffer.popleft()
            return [payload, channel_type]

        # Populate buffer
        try:
            data, self.client_addr = self.socket.recvfrom(BUFFER_SIZE)
        except BlockingIOError:
            return None

        packet = self.parse_packet(data)

        # Unreliable channel, return packet immediately
        if packet.channel_type == 0:
            return [packet.payload, packet.channel_type]

        # To get the first sequence number
        if self.first_reliable_packet:
            self.expected_sequence = packet.seq_num
            self.first_reliable_packet = False
            self._start_waiting(self.expected_sequence)

        if self._has_been_delivered(packet.seq_num):  # Case 1: Duplicate packet already delivered (behind window)
            print(f"[RELIABLE] Duplicate packet SeqNo={packet.seq_num} (Expected={self.expected_sequence})")
            self._send_ack(packet.seq_num)  # Resend ACK
        elif self._is_within_receive_window(packet.seq_num):  # Case 2: Packet within receive window
            if packet.seq_num not in self.reliable_buffer:  # Case 2a: New packet, buffer it
                self.reliable_buffer[packet.seq_num] = packet
                print(
                    f"[RELIABLE] Stored packet SeqNo={packet.seq_num} within window "
                    f"(Expected={self.expected_sequence}, Buffer_size={len(self.reliable_buffer)})"
                )
            else:  # Case 2b: Duplicate buffered packet
                print(
                    f"[RELIABLE] Ignored duplicate buffered SeqNo={packet.seq_num}")
                
            # Always ACK packets within window
            self._send_ack(packet.seq_num)

            # Try to deliver consecutive packets
            self._drain_in_order()

        else:  # Case 3: Packet outside receive window
            print(
                f"[RELIABLE] Packet SeqNo={packet.seq_num} outside receive window "
                f"(Expected={self.expected_sequence}, Window=[{self.expected_sequence}, "
                f"{(self.expected_sequence + self.window_size - 1) % MAX_SEQ_NUM}])"
            )
            # don't send ACK for out-of-window packets

        # Return data if available after processing
        if self.output_buffer:
            payload, channel_type = self.output_buffer.popleft()
            return [payload, channel_type]

        return None

    def _start_waiting(self, seq_num: int):
        """Start tracking wait time for a specific sequence number."""
        if self.waiting_for_seq != seq_num:
            self.waiting_for_seq = seq_num
            self.waiting_start_time = time.time()
            print(f"[TIMEOUT] Started waiting for SeqNo={seq_num}")

    def _check_timeout(self):
        """Check if we've been waiting too long for expected_sequence, and skip it if so."""
        if self.waiting_start_time is None:
            return

        elapsed = time.time() - self.waiting_start_time

        # If we are still waiting for the same packet and timeout has expired
        if (self.waiting_for_seq == self.expected_sequence and elapsed >= self.timeout_threshold):

            print(
                f"[TIMEOUT] Packet SeqNo={self.expected_sequence} timed out after {elapsed:.3f}s "
                f"(threshold={self.timeout_threshold}s). Skipping..."
            )

            # Skip this packet and move window forward
            self.expected_sequence = (self.expected_sequence + 1) % MAX_SEQ_NUM

            # Try to deliver any consecutive packets that are now deliverable
            self._drain_in_order()

            # Reset timeout tracking if we're not already waiting for the new expected
            if self.expected_sequence in self.reliable_buffer:
                # We have the next packet, no need to wait
                self.waiting_start_time = None
                self.waiting_for_seq = None
            else:
                # Start waiting for the new expected sequence
                self._start_waiting(self.expected_sequence)

    def _send_ack(self, seq_num: int):
        """Send ACK for a specific sequence number."""
        if self.client_addr is not None:
            ack_pkt = self.create_ack_packet(seq_num)
            self.socket.sendto(ack_pkt, self.client_addr)

    def _drain_in_order(self):
        """Move buffered packets into output buffer while continuous."""
        delivered_any = False

        while self.expected_sequence in self.reliable_buffer:
            packet = self.reliable_buffer.pop(self.expected_sequence)
            self.output_buffer.append((packet.payload, packet.channel_type))
            print(f"[RELIABLE] Delivered SeqNo={self.expected_sequence}")
            self.expected_sequence = (self.expected_sequence + 1) % MAX_SEQ_NUM
            delivered_any = True

        # If delivered, update wait tracking
        if delivered_any:
            if self.expected_sequence in self.reliable_buffer:
                # Next packet is already buffered, no need to wait
                self.waiting_start_time = None
                self.waiting_for_seq = None
            else:
                # Start waiting for new expected sequence
                self._start_waiting(self.expected_sequence)

    def _is_within_receive_window(self, seq_num: int) -> bool:
        """Check if sequence number is within the current receive window."""
        # Calculate how far ahead seq_num is from the start of our window
        distance_from_window_start = (seq_num - self.expected_sequence) % MAX_SEQ_NUM

        return distance_from_window_start < self.window_size

    def _has_been_delivered(self, seq_num: int) -> bool:
        """Check if packet has already been delivered to upper layer."""
        # This is the packet we're waiting for
        if seq_num == self.expected_sequence:
            return False  # Not delivered yet

        # Calculate circular distance behind expected_sequence
        distance_behind = (self.expected_sequence - seq_num) % MAX_SEQ_NUM

        # 1 to HALF_SEQ_SPACE-1: packet is old (already delivered, can be ignored)
        # ≥ HALF_SEQ_SPACE: packet is actually ahead (future, needs to be stored)
        return 0 < distance_behind < HALF_SEQ_SPACE

    def receive_packet(self):
        """Compatibility shim for existing callers; delegates to get_data."""
        return self.get_data()

    def close(self):
        self.socket.close()
