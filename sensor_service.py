import serial
import serial.tools.list_ports
import re
import time
import threading
from conf_service import cargar_config
from logs_service import log


running = False
MIN_INTERVALO_SEG = 5
hilo_sensores = None

# ------------------------------------------------------------------------------
# SECCIÓN: BUSQUEDA DE ARDUINO
# ------------------------------------------------------------------------------

def find_arduino():
    """Busca y retorna el puerto donde se encuentra el Arduino."""
    ports = serial.tools.list_ports.comports()
    for port in ports:
        if any(
                x in port.description or x in port.device
                for x in ["Arduino", "ttyUSB", "ttyACM"]
            ):
            return port.device
    return None

# ------------------------------------------------------------------------------
# SECCIÓN: CONTROL DE EJECUCIÓN DEL SERVICIO
# ------------------------------------------------------------------------------

def iniciar_lectura(call_guardar_lectura):
    """
    Lanza la ejecución de leer_datos en un hilo independiente.

    Args: 
        call_guardar_lectura (function) - Función para guardar las lecturas.
    """
    global running, hilo_sensores
    running = True
    hilo_sensores = threading.Thread(
        target=leer_datos, 
        args=(call_guardar_lectura,), 
        daemon=True
    )
    hilo_sensores.start()
    log.info("[SENSORS] Servicio de lectura de sensores iniciado.")


def detener_lectura():
    """Detiene el ciclo de lectura de forma segura"""
    global running
    if running:
        running = False
        log.info("[SENSORS] Servicio de lectura de sensores finalizado.")

# ------------------------------------------------------------------------------
# SECCIÓN: LECTURA DE DATOS DESDE EL ARUDUINO
# ------------------------------------------------------------------------------

def leer_datos(call_guardar_lectura):
    """
    Lee datos capturado por los sensores.
    
    Args: call_guardar_lectura - Función encargada de guardar la lectura.
    """
    global running

    mapeo = {
        "DO (mg/L)": "od",
        "PH": "ph",
        "COND (µS/cm)": "con",
        "Turbidity (NTU)": "tur",
        "TDS(ppm)": "tsd",
        "TEMP (C)": "tem"
    }

    while running:
        arduino_port = find_arduino()
        
        if not arduino_port:
            log.warning("[SENSORS] Arduino no detectado. Reintentando en 10s...")
            time.sleep(10)
            continue

        try:
            with serial.Serial(arduino_port, 9600, timeout=2) as arduino:
                log.info(f"[SENSORS] Arduino conectado en el puerto {arduino_port}.")

                time.sleep(2)

                while running:

                    arduino.reset_input_buffer()
                    time.sleep(0.1)             # Espera la eliminación del buffer
                    
                    lectura_actual = {k: None for k in mapeo.values()}
                    start_time = time.time()    
                    
                    # Lectura
                    while running and any(v is None for v in lectura_actual.values()):
                        if (time.time() - start_time) > 10: # Intenta lee por 10s
                            break                           # Si no lee, cierra

                        if arduino.in_waiting > 0:
                            time.sleep(0.1)     # Espera la escritura del arduino
                            try:
                                bin_data = arduino.readline()

                                if not bin_data: continue

                                raw_data = bin_data.decode('utf-8', errors='ignore').strip()
                                match = re.match(r"(.+?):\s*(-?\d+\.?\d*)", raw_data)
                                
                                if match:
                                    etiqueta = match.group(1).strip()
                                    valor = float(match.group(2))
                                    clave = mapeo.get(etiqueta)
                                    if clave:
                                        lectura_actual[clave] = valor

                            except serial.SerialException as e:
                                if "device reports readiness" in str(e):
                                    continue
                                log.warning(f"[SENSORS] Error de comunicación con los sensores: {e}")

                            except Exception as e:
                                log.warning(f"[SENSORS] Error en el procesamiento de los datos de los sensores: {e}")
                                continue

                    # Persistencia
                    if any(v is not None for v in lectura_actual.values()):
                        call_guardar_lectura(lectura_actual.copy())
                        log.info(f"[SENSORS] Lectura guardada: {lectura_actual}.")
                        
                    # Espera interrumpible según config.intervalo_lectura
                    config = cargar_config()
                    intervalo = config.get("intervalo_lectura_seg", 1800) # default 1800s 

                    if intervalo < MIN_INTERVALO_SEG:
                        log.error("[SENSORS] Intervalo de  lectura incorrecto: debe ser >= 5s")
                        break

                    for _ in range(int(intervalo)):
                        if not running: break
                        time.sleep(1)

        except serial.SerialException as e:
            log.error(f"[SENSORS-HARDWARE] Error de conexión con Arduino: {e}")

        except Exception as e:
            log.error(f"[SENSORS] Error inesperado: {e}")

    log.info("[SENSORS] Hilo de lectura finalizado correctamente.")
