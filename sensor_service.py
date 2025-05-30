import serial
import serial.tools.list_ports
import re
import time

def find_arduino():
    ports = serial.tools.list_ports.comports()
    for port in ports:
        if "Arduino" in port.description or "ttyUSB" in port.device or "ttyACM" in port.device:
            return port.device
    return None

def leer_datos(callback):
    mapeo = {
        "DO (mg/L)": "od",
        "PH": "ph",
        "COND (µS/cm)": "con",
        "Turbidity (NTU)": "tur",
        "TDS(ppm)": "tsd"
    }

    lectura_actual = {k: None for k in mapeo.values()}
    arduino_port = find_arduino()

    if arduino_port:
        print(f"Arduino detectado en {arduino_port}")
        arduino = serial.Serial(arduino_port, 9600, timeout=1)
        
        while True:
            if arduino.in_waiting > 0:
                raw_data = arduino.readline().decode('utf-8').strip()
                print(f"Datos recibidos: {raw_data}")

                match = re.match(r"(.+?):\s*(-?\d+\.?\d*)", raw_data)
                if match:
                    etiqueta = match.group(1).strip()
                    valor = float(match.group(2))
                    clave = mapeo.get(etiqueta)
                    if clave:
                        lectura_actual[clave] = valor

                if all(v is not None for v in lectura_actual.values()):
                    callback(lectura_actual.copy())  # Pasamos los datos al callback
                    lectura_actual = {k: None for k in mapeo.values()}
            time.sleep(0.5)
    else:
        print("No se encontró un Arduino conectado.")
