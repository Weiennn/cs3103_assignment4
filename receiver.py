from gameNetAPI import GameNetAPI
import time

def main():
    print("Initializing receiver...")
    server = GameNetAPI(
        mode="server",
        server_addr="localhost",
        server_port=12001,
        timeout=0.2  # 200ms timeout for processing packets
    )
    
    print("Receiver started on localhost:12001. Press Ctrl+C to stop...")
    try:
        while True:
            # Get and process any available data
            data = server._process_socket()
            if data:
                payload, channel_type = data
                channel_name = "RELIABLE" if channel_type == 1 else "UNRELIABLE"
                try:
                    message = payload.decode('utf-8')
                    print(f"[{channel_name}] Message: {message}")
                except UnicodeDecodeError:
                    print(f"[{channel_name}] Binary data ({len(payload)} bytes): {payload.hex()[:20]}...")
            else:
                # Sleep briefly if no data to avoid busy-waiting
                time.sleep(0.1)
                
    except KeyboardInterrupt:
        print("\nShutting down receiver...")
    finally:
        server.close_server()
        print("\nReceiver shutdown complete.")

if __name__ == "__main__":
    main()