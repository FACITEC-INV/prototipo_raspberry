import requests
from db_service import actualizar_enviados, obtener_pendientes
import threading
from conf_service import cargar_config, guardar_config
from logs_service import log

timer = None                # Referencia para el timer
ultimo_intervalo = None     # Controla el timer 

# ------------------------------------------------------------------------------
# SECCIÓN: COMUNICACIÓN CON SERVIDOR (HANDSHAKE)
# ------------------------------------------------------------------------------

def ejecuta_sincronizacion(config):
    """Ejecuta el handshake con el servidor y actualiza la configuración."""
    try:
        _, intervalo_servidor = obtener_info_sincronizacion(
            config["base_url"], 
            config["url_consulta"], 
            config["dispositivo_id"]
        )

        if intervalo_servidor and intervalo_servidor != config.get("intervalo_actualizacion_min"):
            config["intervalo_actualizacion_min"] = intervalo_servidor
            guardar_config(config)
            log.info(f"[SYNC] Cambiando Intervalo a {intervalo_servidor} min.")

    except Exception as e:
        log.error(f"[SYNC] Fallo en la sincronización de configuración: {e}")


def obtener_info_sincronizacion(base_url, url_consulta, dispositivo_id):
    """
    Realiza el handshake de sincronización con el servidor central.

    Args:
        base_url (str): URL base de la API (ej. http://dominio/api).
        url_consulta (str): Endpoint para la sincronización.
        dispositivo_id (str/int): Identificador único del dispositivo.

    Returns:
        tuple: (ultima_conexion, intervalo_actualizacion) o (None, None) si falla.

    Raises:
        No lanza excepciones: Todas las excepciones (Timeout, ConnectionError, 
        HTTPError, etc.) son capturadas internamente para no interrumpir hilo de ejecución.
    """
    try:
        url = f"{base_url}{url_consulta}/{dispositivo_id}"
        response = requests.get(url, timeout=(10, 20))
        response.raise_for_status()               # Lanza error si status!=200
        data = response.json()

        if not isinstance(data, dict):
            log.error("[SYNC] Respuesta inválida del servidor")
            return None, None

        if not data.get('success', False):
            log.error(f"[SYNC] Error en el servidor {data.get('response')}")
            return None, None

        api_response = data.get('response')

        if not isinstance(api_response, dict) or api_response is None:
            log.error("[SYNC] Response inválido o vacío")
            return None, None

        ultima_conexion = api_response.get("ultimaConexion")

        try:
            intervalo_raw = api_response.get("intervaloActualizacion")
            intervalo_actualizacion = int(intervalo_raw) if intervalo_raw is not None else None

        except (ValueError, TypeError):
            log.warning("[SYNC] Intervalo recibido no es numérico. Se ignorará.")
            intervalo_actualizacion = None

        log.info("[SYNC] Handshake exitoso! Dispositivo y servidor comunicados")
        log.info(f"[SYNC] Ultima conexion registada: {ultima_conexion}")
        log.info(f"[SYNC] Intervalo recuperado del server: {intervalo_actualizacion}")
        return ultima_conexion, intervalo_actualizacion

    except requests.exceptions.Timeout:
        log.error("[SYNC] Timeout al consultar el dispositivo para la sincronización")
        return None, None

    except requests.exceptions.ConnectionError:
        log.error("[SYNC] No se pudo conectar al servidor")
        return None, None

    except requests.exceptions.HTTPError as e:
        log.error(f"[SYNC] HTTP error: {e}")
        return None, None
    
    except Exception as e:
        log.error("[SYNC] Error inesperado en la sincronización.")
        log.error(f"[SYNC] Dispositivo: {dispositivo_id}. Error: {e}")
        return None, None

# ------------------------------------------------------------------------------
# SECCIÓN: GESTIÓN DE DATOS (UPLINK)
# ------------------------------------------------------------------------------

def ejecuta_envio(config):
    """Obtiene los datos pendientes de envío y los envía al servidor."""
    try:
        lecturas = obtener_pendientes()
        if not lecturas:
            log.info("[SYNC] Sin datos pendientes de envío.")
            log.info("[SYNC] Operación de envío cancelada.")
            return

        log.info(f"[SYNC] Procesando lote de {len(lecturas)} pendientes...")
        exito, ids_enviados = enviar_lecturas(
            config["base_url"], 
            config["url_envio"], 
            config["dispositivo_id"], 
            lecturas
        )

        if exito:
            actualizar_enviados(ids_enviados)
    except Exception as e:
        log.error(f"[SYNC] Fallo en el proceso de envío de datos: {e}")


def enviar_lecturas(base_url, url_envio, dispositivo_id, lecturas):
    """
    Ejecuta la petición HTTP POST para subir las lecturas al servidor central.

    Args:
        base_url (str): URL base de la API.
        url_envio (str): Endpoint para el upload de datos.
        dispositivo_id (str): ID único del nodo sensor.
        lecturas (list): Lista de objetos del modelo Lectura.

    Returns:
        tuple: (bool, list) Indica si el envío fue exitoso y la lista de IDs.
        
    Raises:
        No lanza excepciones: Manejo interno de errores de transporte y HTTP.
    """

    if not lecturas:
        log.info("[SYNC] Envío cancelado, arg lectura vacío o nulo.")
        return False, []

    # Serialización de datos
    payload = {
        "dispositivoId": dispositivo_id,
        "lecturas": [{
                "fecha": l["timestamp"].isoformat() if l["timestamp"] else None,
                "od": l["od"],
                "ph": l["ph"],
                "con": l["con"],
                "tur": l["tur"],
                "tsd": l["tsd"],
                "tem": l["tem"]
            } for l in lecturas
        ]
    }

    try:
        url = f"{base_url}{url_envio}"
        response = requests.post(
                url,
                json=payload,
                headers={"Content-Type": "application/json"},
                timeout=(10, 60)
            )

        if response.status_code in [200,201]:
            log.info(f"[SYNC] Se enviaron {len(lecturas)} registros correctamente.")
            ids_procesados = [l["id"] for l in lecturas]
            return True, ids_procesados

        log.error(f"[SYNC] HTTP {response.status_code}: {response.text}")
        return False, []

    except requests.exceptions.RequestException as e:
        log.error(f"[SYNC] Error de conexión al enviar lecturas: {e}")
        return False, []

    except Exception as e:
        log.error(f"[SYNC] Error al enviar lecturas: {e}")
        return False, []


# ------------------------------------------------------------------------------
# SECCIÓN: CONTROL DE HILOS Y CICLOS
# ------------------------------------------------------------------------------

def tarea_periodica():
    """
    Orquestador principal del servicio. 
    Coordina la ejecución de tareas y la reprogramación del timer.
    """
    global timer, ultimo_intervalo

    # 1. Ejecución de Tareas:
    try:
        config = cargar_config()
        ejecuta_sincronizacion(config)
        ejecuta_envio(config)

    except Exception as e:
        log.error(f"[SYNC] Error en la ejecución de tareas: {e}")

    # 2. Reprogramación del timer
    try:
        config_actual = cargar_config()
        intervalo_actual = config_actual.get("intervalo_actualizacion_min", 10)

        if timer and ultimo_intervalo != intervalo_actual:
            timer.cancel()
            log.info(f"[SYNC] Ajustando timer a {intervalo_actual} min.")

        ultimo_intervalo = intervalo_actual
        tiempo_espera = intervalo_actual * 60       # de minutos a segundos

        timer = threading.Timer(tiempo_espera, tarea_periodica)
        timer.daemon = True
        timer.start()
    
    except Exception as e:
        log.error(f"[SYNC] Error fatal al reprogramar el ciclo: {e}")

# ------------------------------------------------------------------------------
# SECCIÓN: INTERFAZ DE CONTROL
# ------------------------------------------------------------------------------

def iniciar_sincronizacion():
    global timer
    timer = threading.Timer(1, tarea_periodica) 
    timer.daemon = True
    timer.start()
    log.info("[SENSORS] Servicio de sincronización iniciado.")

def detener_sincronizacion():
    global timer
    if timer:
        timer.cancel()
        log.info("[SYNC] Servicio de sincronización finalizado.")
