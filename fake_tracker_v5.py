import osmnx as ox
import random
import time
import json
from paho.mqtt import client as mqtt_client
from networkx.exception import NetworkXPointlessConcept

# Load configuration from JSON file
with open('config.json') as f:
    config = json.load(f)

broker = config['broker']
port = config['port']
username = config['username']
password = config['password']
client_id_prefix = config['client_id_prefix']
imei_number = str(config['imei_number'])

# Concatenate imei_number to the topic
topic = config['topic'] + imei_number + '/tracker'

# Function to connect to MQTT broker
def connect_mqtt():
    def on_connect(client, userdata, flags, rc):
        if rc == 0:
            print("\033[92mConnected to MQTT Broker!\033[0m")
            print("\033[94mBusy planning route...\033[0m", flush=True)
        else:
            print(f"\033[91mFailed to connect, return code {rc}\033[0m")

    client = mqtt_client.Client(client_id_prefix + f'-{random.randint(0, 1000)}')
    client.username_pw_set(username, password)
    client.on_connect = on_connect
    client.connect(broker, port)
    return client

# Function to publish messages to MQTT
def publish(client, msg):
    result = client.publish(topic, msg)
    status = result[0]
    if status == 0:
        print(f"Send `{msg}` to topic `{topic}`")
    else:
        print(f"\033[91mFailed to send message to topic {topic}\033[0m")

# Function to simulate tracker speed
def simulate_tracker_speed(points, client, G):
    tag_id = config.get('tag_id')  # Check if tag_id exists in config
    for i in range(len(points) - 1):
        lat1, lon1 = points[i]
        lat2, lon2 = points[i+1]
        try:
            if isinstance(lat1, (int, float)) and isinstance(lon1, (int, float)) and isinstance(lat2, (int, float)) and isinstance(lon2, (int, float)):
                distance = ox.distance.great_circle(lat1, lon1, lat2, lon2)
                edge_result = ox.distance.nearest_edges(G, lon1, lat1, return_dist=True)
                if edge_result:
                    edge, dist = edge_result
                    
                    road_name = G.edges[edge].get('name', 'Unnamed Road')
                    route_number = G.edges[edge].get('ref', 'Unnamed Route')
                    max_speed = G.edges[edge].get('maxspeed')
                    actual_speed = G.edges[edge].get('speed_kph')
                    
                    max_speed = float(max_speed) if max_speed is not None else None
                    actual_speed = float(actual_speed) if actual_speed is not None else None
                    
                    print(f"\033[33mRoad Name: {road_name}\033[0m")
                    print(f"\033[33mRoute Number: {route_number}\033[0m")
                    print(f"\033[33mMax Speed: {max_speed}\033[0m")
                    print(f"\033[33mActual Speed: {actual_speed}\033[0m")
                    
                    if max_speed is not None and actual_speed is not None:
                       lower_bound = max(10, actual_speed - 0.1 * actual_speed)
                       upper_bound = max_speed
                    elif max_speed is not None:
                       lower_bound = max(10, max_speed - 0.1 * max_speed)
                       upper_bound = max_speed
                    elif actual_speed is not None:
                       lower_bound = max(10, actual_speed - 0.1 * actual_speed)
                       upper_bound = actual_speed
                    else:
                       lower_bound = 10
                       upper_bound = 60
                       
                    speed = random.triangular(lower_bound, upper_bound, mode=float((lower_bound + upper_bound) / 2))

                    time_to_travel = distance / (speed * 1000 / 3600)  # Convert speed to meter/second
                    lat_diff = lat2 - lat1
                    lon_diff = lon2 - lon1
                    step_lat = lat_diff / (time_to_travel / 5)
                    step_lon = lon_diff / (time_to_travel / 5)
                    current_lat = lat1
                    current_lon = lon1
                    while abs(current_lat - lat1) < abs(lat_diff) and abs(current_lon - lon1) < abs(lon_diff):
                        speed = round(speed, 2)
                        data = {
                            "latitude": current_lat,
                            "longitude": current_lon,
                            "speed": speed
                        }
                        if tag_id:  # Include tag_id if it exists
                            data["tag_id"] = tag_id
                        msg = json.dumps(data)
                        publish(client, msg)
                        current_lat += step_lat
                        current_lon += step_lon
                        time.sleep(5)
                else:
                    print("\033[91mError: No nearest edge found.\033[0m")
            else:
                print("\033[91mError: Invalid latitude or longitude format.\033[0m")
        except (NetworkXPointlessConcept, ValueError) as e:
            print(f"\033[91mError: {e}\033[0m")

# Main function
def run():
    client = connect_mqtt()
    client.loop_start()
    
    start_latitude = config['start_latitude']
    start_longitude = config['start_longitude']
    end_latitude = config['end_latitude']
    end_longitude = config['end_longitude']
    
    origin_point = (start_latitude, start_longitude)
    destination_point = (end_latitude, end_longitude)
    
    bbox = (max(start_latitude, end_latitude) + 0.01, min(start_latitude, end_latitude) - 0.01,
            max(start_longitude, end_longitude) + 0.01, min(start_longitude, end_longitude) - 0.01)
    
    try:
        G = ox.graph_from_bbox(*bbox, network_type='drive', custom_filter='["highway"~"motorway|motorway_link|trunk|trunk_link|primary|primary_link|secondary|secondary_link|tertiary|tertiary_link|residential|living_street|service"]')

        G = ox.add_edge_speeds(G)
        
        orig_node = ox.distance.nearest_nodes(G, start_longitude, start_latitude)
        dest_node = ox.distance.nearest_nodes(G, end_longitude, end_latitude)
        
        shortest_path = ox.shortest_path(G, orig_node, dest_node, weight='length')
        
        path_coordinates = [(G.nodes[node]['y'], G.nodes[node]['x']) for node in shortest_path]
        for i, coordinate in enumerate(path_coordinates):
            print(f"Node {i+1}: Latitude {coordinate[0]}, Longitude {coordinate[1]}")
        
        simulate_tracker_speed(path_coordinates, client, G)
    except Exception as e:
        print(f"\033[91mError: {e}\033[0m")
    
    client.loop_stop()

if __name__ == '__main__':
    run()

