
#!/bin/bash
# Test runs on loopback (lo)

# Global PIDs for trap
RECEIVER_PID=""
SENDER_PID=""

# Trap SIGINT (Ctrl+C) for cleanup
cleanup() {
    echo -e "\n[!] Caught Ctrl+C. Cleaning up..."
    if [[ -n "$SENDER_PID" ]]; then
        echo "Killing sender (PID $SENDER_PID)..."
        kill $SENDER_PID 2>/dev/null
    fi
    if [[ -n "$RECEIVER_PID" ]]; then
        echo "Killing receiver (PID $RECEIVER_PID)..."
        kill $RECEIVER_PID 2>/dev/null
    fi 
    
    echo "Resetting network configuration..."
    sudo tc qdisc del dev lo root
    sleep 5
    echo "Exiting."
    exit 1
}
trap cleanup SIGINT

# Function to display menu and get user choice
show_menu() {
    echo "=========================================="
    echo "Select Test Scenario:"
    echo "------------------------------------------"
    echo "1. Reliable-only (no network impairments)"
    echo "2. Unreliable-only (no network impairments)"
    echo "3. Reliable with delay and packet loss"
    echo "4. Reliable with delay and packet reordering"
    echo "5. Mixed traffic with all impairments"
    echo "6. Exit"
    echo "=========================================="
    read -p "Enter choice (1-6): " choice
}

# Function to configure network parameters based on test type
configure_network() {
    local test_type=$1
    local iface="lo"
    
    # reset any existing config 
    sudo tc qdisc del dev $iface root 2>/dev/null
    
    case $test_type in
        1|2)
            # Clean network
            echo "No network impairments applied."
            ;;
        3)
            # delay and loss required from user
            read -p "Enter average delay (ms): " delay
            read -p "Enter variation in delay (ms): " variation
            read -p "Enter packet loss percentage (%): " loss
            
            echo "Applying delay ${delay}ms ±${variation}ms and ${loss}% packet loss..."
            sudo tc qdisc add dev $iface root netem delay ${delay}ms ${variation}ms loss ${loss}%
            ;;
        4)
            # delay and reordering parameters required from user
            read -p "Enter average delay (ms): " delay
            read -p "Enter variation in delay (ms): " variation
            read -p "Enter packet reorder percentage (%): " reorder
            read -p "Enter correlation percentage (%): " correlation
            
            echo "Applying delay ${delay}ms ±${variation}ms and ${reorder}% reordering..."
            sudo tc qdisc add dev $iface root netem delay ${delay}ms ${variation}ms reorder ${reorder}% ${correlation}%
            ;;
        5)
            # delay, loss, and reordering required from user
            read -p "Enter average delay (ms): " delay
            read -p "Enter variation in delay (ms): " variation
            read -p "Enter packet loss percentage (%): " loss
            read -p "Enter packet reorder percentage (%): " reorder
            read -p "Enter correlation percentage (%): " correlation

            
            echo "Applying all network impairments..."
            sudo tc qdisc add dev $iface root netem \
                delay ${delay}ms ${variation}ms \
                loss ${loss}% \
                reorder ${reorder}% ${correlation}%
            ;;
    esac
    
    # show current network configuration
    echo -e "\nTest will begin in 5 seconds. Current network configuration:"
    tc qdisc show dev $iface

    # sleep to allow user to view configuration
    sleep 5 
    echo
}

# Function to run the test with specified sender
run_test() {
    local sender_script=$1
    
    # start receiver in background
    echo "[*] Starting receiver..."
    python3 receiver.py &
    RECEIVER_PID=$!
    echo "[*] Receiver PID: $RECEIVER_PID"
    sleep 1

    # start sender application in background
    echo "[*] Starting sender ($sender_script)..."
    python3 "$sender_script" &
    SENDER_PID=$!
    echo "[*] Sender PID: $SENDER_PID"

    # wait for the sender process to complete
    echo "[*] Waiting for sender to complete..."
    wait $SENDER_PID
    echo "[*] Sender finished."

    # give receiver time to process final packets
    echo "[*] Waiting 2s for receiver to process final packets..."
    sleep 2

    # stop the receiver
    echo "[*] Stopping receiver..."
    kill $RECEIVER_PID 2>/dev/null
    wait $RECEIVER_PID 2>/dev/null
    echo "[*] Receiver stopped."
}

while true; do
    show_menu
    
    case $choice in
        1)
            echo -e "\nRunning Test 1: Reliable-only transmission"
            configure_network 1
            run_test "reliable_sender.py"
            ;;
        2)
            echo -e "\nRunning Test 2: Unreliable-only transmission"
            configure_network 2
            run_test "unreliable_sender.py"
            ;;
        3)
            echo -e "\nRunning Test 3: Reliable with delay and loss"
            configure_network 3
            run_test "reliable_sender.py"
            ;;
        4)
            echo -e "\nRunning Test 4: Reliable with delay and reordering"
            configure_network 4
            run_test "reliable_sender.py"
            ;;
        5)
            echo -e "\nRunning Test 5: Mixed traffic with all impairments"
            configure_network 5
            run_test "random_sender.py"
            ;;
        6)
            echo "Exiting..."
            break
            ;;
        *)
            echo "Invalid choice. Please try again."
            continue
            ;;
    esac
    
    # RESET network configuration 
    echo -e "\n[*] Cleaning up network configuration..."
    sudo tc qdisc del dev lo root
    
    echo "=========================================="
    echo " Test complete. Network reset to normal."
    echo "=========================================="
    
    # repeat test if wanted
    read -p "Run another test? (y/n): " another
    [[ $another != "y" ]] && break
done
