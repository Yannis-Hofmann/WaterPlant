
import time
import network
from machine import Pin, ADC
from umqtt.simple import MQTTClient

# Disclaimer: We've used GitHub Copilot to help with generating boilerplate code and for debugging purposes. 
# Used 3rd party libraries: 
# umqtt.simple for MQTT communication (https://pypi.org/project/micropython-umqtt.simple/)

# --- Configuration ---
# Wi-Fi Credentials
WIFI_SSID = "hpi_event"
WIFI_PASSWORD = "noum-zuct-TIY"

MQTT_BROKER_IP = "ctf.ythofmann.de" 
MQTT_PORT = 1883
# MQTT Client ID
PICO_ID = "LivingRoom" 

# Publishing topics
TOPIC_SENSOR_MOISTURE = f"pico/{PICO_ID}/sensor/moisture"
TOPIC_PUMP_STATUS = f"pico/{PICO_ID}/pump/status"

# Subscribing topics
TOPIC_PUMP_COMMAND = f"pico/{PICO_ID}/pump/command"
TOPIC_SENSOR_REQUEST = f"pico/{PICO_ID}/sensor/update"
TOPIC_LED_TOGGLE = f"pico/{PICO_ID}/led/toggle"

# Hardware Setup
moisture_sensor = ADC(Pin(26))
pump = Pin(15, Pin.OUT)
pump.on()
led = Pin("LED", Pin.OUT)

def connect_wifi(ssid, password):
    """Connects the Pico to the specified Wi-Fi network."""
    wlan = network.WLAN(network.STA_IF)
    wlan.active(True)
    wlan.connect(ssid, password)
    print(f"Connecting to Wi-Fi: {ssid}...")
    
    max_wait = 15
    while max_wait > 0:
        if wlan.status() < 0 or wlan.status() >= 3:
            break
        max_wait -= 1
        led.toggle()
        time.sleep(1)

    if wlan.status() != 3:
        raise RuntimeError('Wi-Fi connection failed')
    else:
        ip = wlan.ifconfig()[0]
        print(f'Connected to Wi-Fi. Pico IP: {ip}')
        led.on()
    return wlan

def read_moisture_sensor():
    """Reads the moisture sensor and returns a percentage value."""
    raw_value = moisture_sensor.read_u16()
    # Convert to percentage (0-100%). Lower value means more moisture.
    # We invert it so that a higher percentage means wetter soil.
    humidity_percent = 100 - (raw_value / 65535) * 100
    return round(humidity_percent, 2)

def run_pump(duration_s=5):
    """Activates the pump for a specified duration."""
    print(f"Activating pump for {duration_s} seconds.")
    pump.off()
    time.sleep(duration_s)
    pump.on()
    print("Pump deactivated.")

def publish_sensor_data(client):
    """Reads the sensor and publishes the value to the MQTT broker."""
    moisture = read_moisture_sensor()
    print(f"Publishing to topic '{TOPIC_SENSOR_MOISTURE}': {moisture}%")
    client.publish(TOPIC_SENSOR_MOISTURE, str(moisture))

def publish_pump_status(client, status):
    """Publishes the pump status to the MQTT broker."""
    print(f"Publishing to topic '{TOPIC_PUMP_STATUS}': {status}")
    client.publish(TOPIC_PUMP_STATUS, status)


def mqtt_subscription_callback(topic, msg):
    """Callback function to handle incoming MQTT messages."""
    print(f"Received message on topic '{topic.decode()}': {msg.decode()}")
    
    decoded_topic = topic.decode()

    if decoded_topic == TOPIC_PUMP_COMMAND:
        run_pump()
        
    elif decoded_topic == TOPIC_SENSOR_REQUEST:
        print("Received request for sensor update.")
        publish_sensor_data(mqtt_client)
        
    elif decoded_topic == TOPIC_LED_TOGGLE:
        print("Toggling LED state.")
        led.toggle()

# --- Main Execution ---

# Connect to Wi-Fi
try:
    connect_wifi(WIFI_SSID, WIFI_PASSWORD)
except RuntimeError as e:
    print(e)
    while True:
        led.toggle()
        time.sleep(0.5)

# 2. Connect to MQTT Broker
mqtt_client = MQTTClient(
    client_id=f"pico_client_{PICO_ID}",
    server=MQTT_BROKER_IP,
    port=MQTT_PORT,
    user="pico1",
    password="REDACTED"
    # user="pico2",
    # password="falcon-krypton-climatic"
    # user="pico3",
    # password="follicle-playlist-handbook"
)
mqtt_client.set_callback(mqtt_subscription_callback)

try:
    mqtt_client.connect()
    print(f"Connected to MQTT Broker at {MQTT_BROKER_IP}")
except OSError as e:
    print(f"Failed to connect to MQTT broker: {e}")

mqtt_client.subscribe(TOPIC_PUMP_COMMAND)
mqtt_client.subscribe(TOPIC_SENSOR_REQUEST)
mqtt_client.subscribe(TOPIC_LED_TOGGLE)
print(f"Subscribed to topics: {TOPIC_PUMP_COMMAND}, {TOPIC_SENSOR_REQUEST}, {TOPIC_LED_TOGGLE}")
publish_pump_status(mqtt_client, "ready")


last_publish_time = 0
publish_interval = 60 # seconds

while True:
    try:
        # Check for any pending messages from the broker.
        mqtt_client.check_msg()
        
        # Publish data at regular intervals
        current_time = time.time()
        if (current_time - last_publish_time) > publish_interval:
            publish_sensor_data(mqtt_client)
            last_publish_time = current_time
            
        time.sleep(1) 

    except OSError as e:
        print(f"An error occurred: {e}. Reconnecting...")
        time.sleep(5)
        try:
            mqtt_client.disconnect()
        except:
            pass
        mqtt_client.connect()
        mqtt_client.subscribe(TOPIC_PUMP_COMMAND)
        mqtt_client.subscribe(TOPIC_SENSOR_REQUEST)
        mqtt_client.subscribe(TOPIC_LED_TOGGLE)

