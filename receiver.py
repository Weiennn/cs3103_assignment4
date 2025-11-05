from gameNetAPI import GameNetAPI
import time
from datetime import datetime


def handle_received_data(packet):
    channel_type = packet.channel_type
    channel_name = "RELIABLE" if channel_type == 1 else "UNRELIABLE"
    seq_num = packet.seq_num
    dt_local = datetime.fromtimestamp(packet.time_stamp / 1000)
    ack_num = packet.ack_num
    payload = packet.payload.decode('utf-8') if packet.payload else None
    
    print(
        f"[RECEIVER APPLICATION] Received packet with Channel type: {channel_name} seq_num={seq_num}, "
        f"time_stamp={dt_local.strftime('%Y-%m-%d %H:%M:%S.%f')[:-3]}, ack_num={ack_num}",
        f"Payload: {payload if payload else 'No Payload'}")

def main():
    print("Initializing receiver...")
    server = GameNetAPI(
        mode="server",
        server_addr="localhost",
        server_port=12001,
        timeout=0.2,  # 200ms timeout for processing packets
        callback_function=handle_received_data
    )
    
    print("Receiver started on localhost:12001. Press Ctrl+C to stop...")
    server.start()
    try:
        while True:
            time.sleep(0.1)
                
    except KeyboardInterrupt:
        print("\nShutting down receiver...")
    finally:
        server.close_server()
        print("\nReceiver shutdown complete.")

if __name__ == "__main__":
    main()