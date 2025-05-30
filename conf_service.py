import json

CONFIG_PATH = 'config.json'

def cargar_config():
    with open(CONFIG_PATH, 'r') as f:
        return json.load(f)

def guardar_config(config):
    with open(CONFIG_PATH, 'w') as f:
        json.dump(config, f, indent=4)
