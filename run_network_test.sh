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
python3 receiver2.py &
RECEIVER_PID=$!
sleep 1

# start sender application
echo "[*] Starting sender..."
python3 gameNetClientAPI.py

# kill receiver process some time after sender finishes
sleep 10
echo "[*] Stopping receiver..."
kill $RECEIVER_PID 2>/dev/null

# reset 
echo
echo "[*] Cleaning up netem configuration..."
sudo tc qdisc del dev $iface root

echo "=========================================="
echo " Test complete. Network reset to normal."
echo "=========================================="
