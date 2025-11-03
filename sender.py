import socket
import struct
import time
import random
import json
from gameNetClientAPI import GameNetClientAPI
# import some API 

# Packet header: | ChannelType (1B) | SeqNo (2B) | Timestamp (4B) | Payload |

def data_to_send(line_num) -> tuple[int, str]:
    isReliable = random.randint(0, 1)
    with open('gamedata.txt', 'r') as file:
        for i, line in enumerate(file):
            if i == line_num:
                data = line.strip()

    print(f"Data to send: {data}, isReliable: {isReliable}")
    return isReliable, data

def main():
    # instantiate gameNetAPI 
    RECEIVER_ADDR = 'localhost'
    RECEIVER_PORT = 54321

    SENDER_ADDR = 'localhost'
    SENDER_PORT = 12345
    client = GameNetClientAPI(SENDER_ADDR, SENDER_PORT, RECEIVER_ADDR, RECEIVER_PORT)

    # line_num = 0
    # while line_num < 100:  
    isTransmissionReliable, gameData = data_to_send(0)
    # send data using gameNetAPI
    client.send_packet(gameData, isTransmissionReliable)

if __name__ == "__main__":
    main()