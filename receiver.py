from gameNetAPI import GameNetAPI
import time


def handle_received_data(payload, channel_type):
    channel_name = "RELIABLE" if channel_type == 1 else "UNRELIABLE"
    payload = payload.decode('utf-8', errors='replace')
    print(
        f"[RECEIVER APPLICATION] Channel type: {channel_name} Received: {payload[:100]}")

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
        # while True:
        #     # Get and process any available data
        #     data = server._process_socket()
        #     if data:
        #         payload, channel_type = data
        #         channel_name = "RELIABLE" if channel_type == 1 else "UNRELIABLE"
        #         try:
        #             message = payload.decode('utf-8')
        #             print(f"[{channel_name}] Message: {message}")
        #         except UnicodeDecodeError:
        #             print(f"[{channel_name}] Binary data ({len(payload)} bytes): {payload.hex()[:20]}...")
        #     else:
        #         # Sleep briefly if no data to avoid busy-waiting
        #         time.sleep(0.1)
        while True:
            time.sleep(1)
                
    except KeyboardInterrupt:
        print("\nShutting down receiver...")
    finally:
        server.close_server()
        print("\nReceiver shutdown complete.")

if __name__ == "__main__":
    main()