import threading
import json
import time
from flask import Flask, jsonify, render_template_string
import paho.mqtt.client as mqtt

# --- Configuration ---
MQTT_BROKER_IP = "localhost"
MQTT_PORT = 1883

picos_data = {}
picos_data_lock = threading.Lock()

# --- MQTT Client Setup ---


def on_connect(client, userdata, flags, rc):
    if rc == 0:
        print("Connected to MQTT Broker!")
        client.subscribe("pico/+/sensor/moisture")
        client.subscribe("pico/+/pump/status")
    else:
        print(f"MQTT connection failed: {rc}")


def on_message(client, userdata, msg):
    topic = msg.topic
    payload = msg.payload.decode()
    print(f"Received message on topic {topic}: {payload}")

    try:
        parts = topic.split("/")
        pico_id = parts[1]

        with picos_data_lock:
            if pico_id not in picos_data:
                picos_data[pico_id] = {"sensors": {}, "pump": {}}

            if parts[2] == "sensor":
                sensor_type = parts[3]
                now = time.strftime("%Y-%m-%d %H:%M:%S")

                if sensor_type not in picos_data[pico_id]["sensors"]:
                    picos_data[pico_id]["sensors"][sensor_type] = {
                        "value": payload,
                        "timestamp": now,
                        "history": [],
                    }

                # Append to history
                picos_data[pico_id]["sensors"][sensor_type]["history"].append(
                    {"value": float(payload), "timestamp": now}
                )

                # Store current value
                picos_data[pico_id]["sensors"][sensor_type]["value"] = payload
                picos_data[pico_id]["sensors"][sensor_type]["timestamp"] = now

                # Moisture threshold logic
                last_run = picos_data[pico_id]["pump"].get("status")
                if last_run == "ready":
                    return
                if float(payload) < 30 and (
                    not last_run
                    or time.time()
                    - time.mktime(time.strptime(last_run, "%Y-%m-%d %H:%M:%S"))
                    > 172800
                ):
                    print(
                        f"Moisture low ({payload}) → auto-activating pump on pico {pico_id}"
                    )
                    run_pump(pico_id)

            elif parts[2] == "pump" and parts[3] == "status":
                picos_data[pico_id]["pump"] = {"status": payload}

    except Exception as e:
        print(f"Error processing topic '{topic}': {e}")


def setup_mqtt_client():
    client = mqtt.Client()
    client.username_pw_set("server", "REDACTED")
    client.on_connect = on_connect
    client.on_message = on_message
    client.connect(MQTT_BROKER_IP, MQTT_PORT, 60)
    return client


# --- Flask Web Server ---

app = Flask(__name__)


@app.route("/plants")
def index():
    with picos_data_lock:
        current_data = json.loads(json.dumps(picos_data))
    return render_template_string(webpage(current_data), picos=current_data)


@app.route("/plants/api/pico/<pico_id>/pump/run", methods=["POST"])
def run_pump(pico_id):
    topic = f"pico/{pico_id}/pump/command"
    print(f"Publishing run command to {topic}")
    mqtt_client.publish(topic, "run")
    last_run_time = time.strftime("%Y-%m-%d %H:%M:%S")
    with picos_data_lock:
        picos_data[pico_id]["pump"]["status"] = last_run_time
    return jsonify({"status": "success", "last_run": last_run_time})


@app.route("/plants/api/pico/<pico_id>/sensor/update", methods=["POST"])
def update_sensor(pico_id):
    topic = f"pico/{pico_id}/sensor/update"
    mqtt_client.publish(topic, "update")
    return jsonify({"status": "success"})


@app.route("/plants/api/pico/<pico_id>/led/toggle", methods=["POST"])
def toggle_light(pico_id):
    topic = f"pico/{pico_id}/led/toggle"
    mqtt_client.publish(topic, "toggle")
    return jsonify({"status": "success"})


# --- HTML Template with Chart.js added ---
def webpage(picos):
    pico_sections = ""
    if not picos:
        pico_sections = "<p>No Picos have reported in yet. Make sure they are running and connected.</p>"
    else:
        for pico_id, data in picos.items():
            moisture_history_data = data["sensors"].get("moisture", {}).get("history", [])
            moisture_history_json = json.dumps(moisture_history_data)

            pico_sections += f"""
                <div class="pico-section">
                    <h2>
                        Pico {pico_id}
                        <button class="btn" onclick="togglePicoLight('{pico_id}')">Toggle Light</button>
                    </h2>
                    <div class="stats-grid">
            """

            for sensor, details in data["sensors"].items():
                pico_sections += f"""
                    <div class="stat-card">
                        <div class="stat-label">{sensor.capitalize()}</div>
                        <div class="stat-value">{details['value']}</div>
                        <div class="stat-timestamp">{details['timestamp']}</div>
                        <button class="btn" onclick="updateSensor('{pico_id}')">Update Sensor</button>
                    </div>
                """

            pump_status = data["pump"].get("status", "No data")
            status_display = f"Last Run: {pump_status}" if pump_status else "Ready"

            pico_sections += f"""
                    <div class="stat-card pump-card">
                        <div class="stat-label">Pumpe</div>
                        <div class="stat-value small" id="pico-{pico_id}-pump-status">{status_display}</div>
                        <button class="btn" onclick="waterPlants('{pico_id}')">Wasser!</button>
                    </div>
                    </div>

                    <canvas id="moistureChart-{pico_id}" width="600" height="200"></canvas>
                    <script>
                        const ctx_{pico_id} = document.getElementById('moistureChart-{pico_id}').getContext('2d');
                        const data_{pico_id} = {moisture_history_json};

                        const labels_{pico_id} = data_{pico_id}.map(x => x.timestamp);
                        const values_{pico_id} = data_{pico_id}.map(x => x.value);

                        new Chart(ctx_{pico_id}, {{
                            type: 'line',
                            data: {{
                                labels: labels_{pico_id},
                                datasets: [{{
                                    label: 'Moisture (%)',
                                    data: values_{pico_id},
                                    fill: true,
                                    borderColor: 'rgba(52,152,219,1)',
                                    backgroundColor: 'rgba(52,152,219,0.2)',
                                    tension: 0.1
                                }}]
                            }},
                            options: {{
                                responsive: true,
                                scales: {{
                                    x: {{
                                        title: {{
                                            display: true,
                                            text: 'Zeit'
                                        }}
                                    }},
                                    y: {{
                                        beginAtZero: true,
                                        max: 100,
                                        title: {{
                                            display: true,
                                            text: 'Feuchtigkeit (%)'
                                        }}
                                    }}
                                }}
                            }}
                        }});
                    </script>
                </div>
            """

    return f"""
    <!DOCTYPE html>
    <html>
    <head>
        <title>Smart Plant Dashboard</title>
        <style>
            body {{ font-family: Arial; background: #f2f2f2; padding: 20px; }}
            .pico-section {{ background: #fff; padding: 20px; margin-bottom: 30px; border-radius: 8px; box-shadow: 0 1px 4px rgba(0,0,0,0.1); }}
            .stats-grid {{ display: flex; gap: 20px; flex-wrap: wrap; }}
            .stat-card {{ flex: 1 1 200px; background: #f9f9f9; padding: 20px; border-radius: 8px; }}
            .stat-label {{ font-weight: bold; margin-bottom: 5px; }}
            .stat-value {{ font-size: 1.5em; color: #3498db; }}
            .stat-value.small {{ font-size: 1em; color: #888; }}
            .stat-timestamp {{ font-size: 0.9em; color: #777; margin-top: 5px; }}
            .btn {{ background: #3498db; color: white; border: none; padding: 8px 12px; border-radius: 5px; cursor: pointer; }}
            .btn:hover {{ background: #2980b9; }}
        </style>
        <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
    </head>
    <body>
        <h1>Smart Plant Monitor</h1>
        {pico_sections}

        <script>
            setInterval(() => window.location.reload(), 15000);

            async function waterPlants(picoId) {{
                const el = document.getElementById(`pico-${{picoId}}-pump-status`);
                el.innerText = "Bewässert...";
                const res = await fetch(`/plants/api/pico/${{picoId}}/pump/run`, {{ method: "POST" }});
                const data = await res.json();
                setTimeout(() => {{
                    el.innerText = `Last Run: ${{data.last_run}}`;
                }}, 3000);
            }}

            async function togglePicoLight(picoId) {{
                await fetch(`/plants/api/pico/${{picoId}}/led/toggle`, {{ method: "POST" }});
            }}

            async function updateSensor(picoId) {{
                await fetch(`/plants/api/pico/${{picoId}}/sensor/update`, {{ method: "POST" }});
                setTimeout(() => window.location.reload(), 2000);
            }}
        </script>
    </body>
    </html>
    """


# --- Main ---
if __name__ == "__main__":
    mqtt_client = setup_mqtt_client()
    threading.Thread(target=mqtt_client.loop_forever, daemon=True).start()
    print("Webinterface verfügbar unter http://localhost:8080")
    app.run(host="0.0.0.0", port=8080)
