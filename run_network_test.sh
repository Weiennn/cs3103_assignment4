#!/bin/bash
# Test runs on loopback (lo)

# Prompt user for parameters
read -p "Enter average delay (ms): " delay
read -p "Enter variation in delay (ms): " variation
read -p "Enter packet loss percentage (%): " loss
read -p "Enter packet reorder percentage (%): " reorder
read -p "Enter correlation percentage (%): " correlation

iface="lo"

echo
echo "=========================================="
echo " Configuring network emulation on $iface"
echo "------------------------------------------"
echo " Delay: ${delay}ms ±${variation}ms"
echo " Packet Loss: ${loss}%"
echo " Reordering: ${reorder}% (correlation ${correlation}%)"
echo "=========================================="
echo

# remove any previous qdisc 
sudo tc qdisc del dev $iface root 2>/dev/null

# apply new netem configuration as speciifed by user
sudo tc qdisc add dev $iface root netem \
    delay ${delay}ms ${variation}ms \
    loss ${loss}% \
    reorder ${reorder}% ${correlation}%

echo "Applied configuration:"
tc qdisc show dev $iface
echo

# start receiver in background
echo "[*] Starting receiver..."
python3 receiver.py &
RECEIVER_PID=$!
echo "[*] Receiver PID: $RECEIVER_PID"
sleep 1

# start sender application in background
echo "[*] Starting sender..."
python3 sender.py &
SENDER_PID=$!
echo "[*] Sender PID: $SENDER_PID"

# Wait for the SENDER process to complete
echo "[*] Waiting for sender (PID $SENDER_PID) to complete its run..."
wait $SENDER_PID
echo "[*] Sender finished."

# Give receiver a moment to process any final packets (like the session summary)
echo "[*] Waiting 2s for receiver to process final packets..."
sleep 2

# Stop the receiver using SIGINT (Ctrl+C) to trigger its graceful shutdown
echo "[*] Stopping receiver (PID $RECEIVER_PID)..."
kill $RECEIVER_PID 2>/dev/null

# Wait for the receiver process to fully terminate
wait $RECEIVER_PID 2>/dev/null
echo "[*] Receiver stopped."

# reset 
echo
echo "[*] Cleaning up netem configuration..."
sudo tc qdisc del dev $iface root

echo "=========================================="
echo " Test complete. Network reset to normal."
echo "=========================================="
