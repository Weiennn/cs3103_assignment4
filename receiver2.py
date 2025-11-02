# receiver.py
from gameNetServer import GameNetServer
import time

def packet_handler(payload, channel_type):
    """
    Custom callback function to handle received packets
    """
    channel_name = "RELIABLE" if channel_type == 1 else "UNRELIABLE"
    
    # Try to decode as text, otherwise show as hex
    try:
        message = payload.decode('utf-8')
        print(f"[{channel_name}] Message: {message}")
    except UnicodeDecodeError:
        print(f"[{channel_name}] Binary data ({len(payload)} bytes): {payload.hex()[:20]}...")
    
    # Add your custom processing logic here
    # For example, save to file, update GUI, etc.

def main():
    # Create server with your custom callback
    server = GameNetServer(
        addr="localhost",
        port=54321,
        timeout_threshold=0.7,
        callback_function=packet_handler
    )
    
    # Start the server
    server.start()
    
    try:
        print("Receiver started. Press Ctrl+C to stop...")
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\nShutting down...")
    finally:
        server.close()
        server.print_metrics()

if __name__ == "__main__":
    main()