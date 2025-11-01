#!/bin/bash
# ==========================================
# Adaptive Hybrid Transport Protocol Test
# Network Emulation Runner (Loopback only)
# ==========================================

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

# Ensure previous qdisc is removed
sudo tc qdisc del dev $iface root 2>/dev/null

# Apply new netem configuration
sudo tc qdisc add dev $iface root netem \
    delay ${delay}ms ${variation}ms \
    loss ${loss}% \
    reorder ${reorder}% ${correlation}%

# Verify settings
echo "Applied configuration:"
tc qdisc show dev $iface
echo

# Start receiver in background
echo "[*] Starting receiver..."
python3 receiver.py &
RECEIVER_PID=$!
sleep 1

# Start sender
echo "[*] Starting sender..."
python3 sender.py

# Kill receiver after sender finishes
echo "[*] Stopping receiver..."
kill $RECEIVER_PID 2>/dev/null

# Remove network emulation
echo
echo "[*] Cleaning up netem configuration..."
sudo tc qdisc del dev $iface root

echo "=========================================="
echo " Test complete. Network reset to normal."
echo "=========================================="
