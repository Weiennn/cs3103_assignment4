import socket
import struct
import time
import random
import json
import datetime
from gameNetServer import GameNetServer

SERVER_ADDR = "localhost"
SERVER_PORT = 54321

# Packet header: | ChannelType (1B) | SeqNo (2B) | Timestamp (4B) | Payload |

def main():
    server = GameNetServer(addr=SERVER_ADDR, port=SERVER_PORT)
    print(f"GameNetServer initialized on {SERVER_ADDR}:{SERVER_PORT}")

    inactivity_limit = 10  # seconds
    last_packet_time = time.time()

    try:
        while True:
            packet_data = server.get_data()
            if packet_data:
                last_packet_time = time.time()
                payload, channel_type, time_stamp, seq_num = packet_data

                channel_type = "Unreliable" if channel_type == 0 else "Reliable"
                seq_num = None if channel_type == "Unreliable" else seq_num

                recv_time_stamp=int(datetime.datetime.now().timestamp())
                RTT = recv_time_stamp - time_stamp
                try:
                    decoded = payload.decode('utf-8')
                except Exception:
                    decoded = repr(payload)
                print("-----------------------")
                print(f"Channel Type: {channel_type}")
                print(f"Payload: {decoded}")
                print(f"Sent Timestamp: {time_stamp}")
                print(f"Received Timestamp: {recv_time_stamp}")
                print(f"Sequence Number: {seq_num}")
                print(f"RTT: {RTT} seconds")
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