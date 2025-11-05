import time
import random
from gameNetAPI import GameNetAPI

def data_to_send(line_num: int) -> tuple[int, bytes]:
    """
    Read a specific line from gamedata.txt and randomly decide reliability.
    Returns (channel_type, payload) where channel_type is:
    - 1 for reliable transmission
    - 0 for unreliable transmission
    This function always chooses reliable transmission for each line.
    """
    try:
        with open('gamedata.txt', 'r') as file:
            lines = file.readlines()
            if line_num < len(lines):
                data = lines[line_num].strip()
                # always unreliable transmission, for demonstration purposes
                channel_type = 0
                print(f"Line {line_num}: {data} -> {'Reliable' if channel_type == 1 else 'Unreliable'}")
                return channel_type, data.encode('utf-8')
            else:
                return None
    except FileNotFoundError:
        print("Error: gamedata.txt not found!")
        return None
    except Exception as e:
        print(f"Error reading gamedata.txt: {e}")
        return None

def main():
    print("Initializing sender...")
    
    # Create GameNetAPI in client mode
    client = GameNetAPI(
        mode="client",
        client_addr="localhost",
        client_port=12345,
        server_addr="localhost",
        server_port=12001,  # Match the receiver's port
        timeout=0.2  # 200ms timeout
    )

    print("Sender started. Sending data from gamedata.txt...")
    
    try:
        line_num = 0
        while True:
            result = data_to_send(line_num)
            if line_num >= len(open('gamedata.txt').readlines()):
                print("Reached end of file.")
                break
            elif result is None:
                print("An error occurred.")
                break

            channel_type, payload = result
            client.send_packet(payload, channel_type)
            
            line_num += 1
            # Small delay between sends to avoid overwhelming the receiver
            time.sleep(0.1)
            
    except KeyboardInterrupt:
        print("\nSending interrupted by user.")
    finally:
        # Clean shutdown: close client and print statistics
        print("\nClosing sender connection...")
        client.close_client()  # This will send session summary to server
        
        # print("\nSender Statistics:")
        # print(f"Total reliable packets sent: {client.total_reliable_sent}")
        # print(f"Total unreliable packets sent: {client.total_unreliable_sent}")
        # print("Shutdown complete.")

if __name__ == "__main__":
    main()