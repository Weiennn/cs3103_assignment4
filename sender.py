import socket
import struct
import time
import random
import json
# import some API 

# Packet header: | ChannelType (1B) | SeqNo (2B) | Timestamp (4B) | Payload |

def data_to_send(line_num):
    isReliable = random.randint(0, 1)
    with open('gamedata.txt', 'r') as file:
        for i, line in enumerate(file):
            if i == line_num:
                data = line.strip()

    print(f"Data to send: {data}, isReliable: {isReliable}")    
    return isReliable, data

def main():
    # instantiate gameNetAPI 
    ## create here

    line_num = 0
    while line_num < 100:  
        isTransmissionReliable, data_to_send = data_to_send(line_num)
        # send data using gameNetAPI
        ## gameNetAPI.send(data_to_send, isTransmissionReliable)