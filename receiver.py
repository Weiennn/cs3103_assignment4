import socket
import struct
import time
import random
import json
from gameNetServer import GameNetServer

# Packet header: | ChannelType (1B) | SeqNo (2B) | Timestamp (4B) | Payload |


def main():
    server = GameNetServer(addr='localhost', port=54321)
    print("GameNetServer initialized on localhost:54321")

    inactivity_limit = 5  # seconds
    last_packet_time = time.time()

    try:
        while True:
            packet_data = server.get_data()
            if packet_data:
                last_packet_time = time.time()
                payload, channel_type = packet_data
                try:
                    decoded = payload.decode('utf-8')
                except Exception:
                    decoded = repr(payload)
                print(f"Channel Type: {channel_type}")
                print(f"Payload: {decoded}")
                print("-----------------------")
            else:
                time.sleep(0.1)

            # Exit if no packet received for inactivity_limit seconds
            if time.time() - last_packet_time > inactivity_limit:
                print(f"No packets received for {inactivity_limit} seconds. Exiting receiver.")
                break

    except KeyboardInterrupt:
        print("Shutting down receiver (KeyboardInterrupt)")
    finally:
        server.close()
        print("Server socket closed")


if __name__ == "__main__":
    main()