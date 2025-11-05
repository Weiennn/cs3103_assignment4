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
    
    INACTIVITY_TIMEOUT = 10  # seconds
    last_packet_time = time.time()
    
    print(f"Receiver started on localhost:12001. Will exit after {INACTIVITY_TIMEOUT}s of inactivity...")
    try:
        while True:
            # Get and process any available data
            data = server._process_socket()
            if data:
                last_packet_time = time.time()  # Reset timer on packet received
                payload, channel_type = data
                channel_name = "RELIABLE" if channel_type == 1 else "UNRELIABLE"
                try:
                    message = payload.decode('utf-8')
                    print(f"[{channel_name}] Message: {message}")
                except UnicodeDecodeError:
                    print(f"[{channel_name}] Binary data ({len(payload)} bytes): {payload.hex()[:20]}...")
            else:
                # Check for inactivity timeout
                if time.time() - last_packet_time > INACTIVITY_TIMEOUT:
                    print(f"\nNo packets received for {INACTIVITY_TIMEOUT} seconds. Exiting...")
                    break

            # Sleep briefly if no data to avoid busy-waiting
            time.sleep(0.1)
                
    except KeyboardInterrupt:
        print("\nShutting down receiver...")
    finally:
        server.close_server()
        print("\nReceiver shutdown complete.")

if __name__ == "__main__":
    main()