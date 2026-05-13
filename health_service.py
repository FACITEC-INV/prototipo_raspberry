import os
import subprocess
import requests
import threading
import time
from conf_service import cargar_config
from enum import Enum
from logs_service import log
from db_service import obtener_fecha_ultimo_registro as obfech

 # Ruta del sensor térmico del SoC
TEMPERATURE_FILE_DIR = "/sys/class/thermal/thermal_zone0/temp"

POWERDOWN_BIT0 = 0x1        # Bit0: under-voltage detectado actualmente
POWERDOWN_BIT16= 0x10000    # Bit16: under-voltage ocurrido desde último arranque

power_fails_counter = 0     # Contador de fallos de energía consecutivos
power_restart_counter = 0   # Contador de ciclos sin fallo tras modo rápido
power_is_fast_mode = False  # Modo de monitoreo acelerado mientras hay fallos
power_next_time = 0         # Próxima ejecución del diagnóstico de energía
general_next_time = 0       # Próxima ejecución del diagnóstico general

_isRunning = False          # Flag de control del bucle principal del servicio
_health_thread = None       # Referencia al hilo del servicio de autodiagnóstico


# ------------------------------------------------------------------------------
# SECCIÓN: Especificación de estados del sistema y retorno de funciones
# ------------------------------------------------------------------------------

class Status(Enum):
    OK          =   "OK"
    WARNING     =   "WARNING"
    CRITICAL    =   "CRITICAL"
    ERROR       =   "ERROR"
    OFFLINE     =   "OFFLINE"


def _resolved(status, value, message):
    """Retorno de las funciones de diagnóstico."""
    return {
        "status": status,
        "value": value,
        "message": message
    }


# ------------------------------------------------------------------------------
# SECCIÓN: FUNCIONES DE VERIFICACIóN DEL HARDWARE DEL DISPOSITIVO
# ------------------------------------------------------------------------------

## Temperatura ##
def _temperature_diagnose(limits):
    """Diagnostica la temperatura del sistema.

    Lee la temperatura desde temperature_file_dir (valor en miligrados /1000)
    y la compara con los límites recibidos como parámetro.

    ARGS:
        limits: dict con {"warning": int, "critical": int}

    Returns:
        dict: {"status": Status, "value": float, "message": str}
    """
    try:
        temperature = 0
        if os.path.exists(TEMPERATURE_FILE_DIR):
            with open(TEMPERATURE_FILE_DIR, "r") as file:
                temperature = int(file.read())/1000
        else:
            raise Exception(f"Error al leer la temperatura del sistema")
        if temperature >= limits["critical"]:
            return _resolved(Status.CRITICAL, temperature, "Temperatura CRÍTICA")
        elif temperature >= limits["warning"]:
            return _resolved(Status.WARNING, temperature, "Temperatura WARNING")
        else:
            return _resolved(Status.OK, temperature, "Temperatura OK")
    except Exception as e:
        log.error(f"[HEALTH] Error en _temperature_diagnose. {e}")
        return _resolved(Status.ERROR, 0, f"{e}")


## Espacio del SD ##
def _disk_diagnose(limits):
    """Diagnostica el espacio libre en disco.
    
    Calcula el espacio libre en la partición raíz (/) usando os.statvfs()
    y lo compara con los límites configurados.
    
    Args:
        limits: dict con {"warning": int, "critical": int} (en GB)
    
    Returns:
        dict: {"status": Status, "value": float, "message": str}
    """
    try:
        stat = os.statvfs("/")
        frsize = stat.f_frsize
        bavail = stat.f_bavail
        free = (frsize * bavail) / (1024 ** 3) # GB
        if free <= limits["critical"]:
            return _resolved(Status.CRITICAL, round(free, 1), "Espacio CRÍTICO")
        elif free <= limits["warning"]:
            return _resolved(Status.WARNING, round(free, 1), "Espacio WARNING")
        else:
            return _resolved(Status.OK, round(free, 1), "Espacio OK")
    except Exception as e:
        log.error(f"[HEALTH] Error en _power_diagnose. {e}")
        return _resolved(Status.ERROR, 0, f"{e}")


## Energía ##
def _power_diagnose():
    """
    Diagnostica el estado de energía y throttling del Raspberry Pi.
    
    Returns:
        tuple: (hex_val, bit0, bit16)|(Status.ERROR, error_msg)
    """
    try:
        bit0, bit16 = False, False
        cmdresult = subprocess.run(
            ['vcgencmd', 'get_throttled'],
            capture_output=True,
            text=True,
            timeout=5
        )
        if cmdresult.returncode != 0:
            raise Exception("Error al leer los datos de la energía")
        output = cmdresult.stdout.strip()
        if "=" in output:
            diag_val = int(output.split('=')[1], 16)
            if diag_val & POWERDOWN_BIT0:
                bit0 =  True
            if diag_val & POWERDOWN_BIT16:
                bit16 = True
            return ( f"{diag_val:#x}", bit0, bit16)
        else:
            raise Exception(f"Respuesta inesperada: {output}")
    except Exception as e:
        log.error(f"[HEALTH] Error en _power_diagnose. {e}")
        return (Status.ERROR, f"{e}")


def _power_diagnose_controller():
    """
    Controla el estado de energía usando un sistema de contadores y modos.
    
    Globals:
        - power_fails_counter: Contador de fallos consecutivos
        - power_restart_counter: Contador de ciclos de restauración
        - power_is_fast_mode: Modo rápido activo durante fallos
    
    Returns:
        dict: {"status": Status, "value": float, "message": str}
    """
    global power_fails_counter, power_restart_counter, power_is_fast_mode
    try:
        power_data = _power_diagnose()
        if power_data[0] == Status.ERROR:
            raise Exception(power_data[1])
        hex_val, bit0, bit16 = power_data
        if bit0:
            power_fails_counter += 1
            power_restart_counter = 0
            power_is_fast_mode = True
        else:
            power_fails_counter = 0
            if power_is_fast_mode:
                power_restart_counter += 1
        if power_fails_counter >= 8:
            return _resolved(Status.CRITICAL, hex_val, "Energía CRÍTICA")
        if not bit0 and (not power_is_fast_mode or power_restart_counter >= 5):
            power_is_fast_mode = False
            power_restart_counter = 0
            msg = "Energía OK" + ("-(Restaurada)" if bit16 else "")
            return _resolved(Status.OK, hex_val, msg)
        return _resolved(Status.WARNING, hex_val, "Energía WARNING-(Verificando)")
    except Exception as e:
        log.error(f"[HEALTH] Error en _power_diagnose_controller. {e}")
        return _resolved(Status.ERROR, 0, f"{e}")


## Arduino ##
def _arduino_diagnose(limits):
    """
    Diagnostica el estado del Arduino basado en el tiempo
    transcurrido desde su último registro.
    
    Args:
        limits: dict con {"warning": int, "critical": int} (en segundos)
    
    Returns:
        dict: {"status": Status, "value": float, "message": str}
    """
    try:
        lastRec = obfech()
        if lastRec is None:
            return _resolved(Status.OFFLINE, lastRec, "Sin registros en la DB")
        limit_critical = limits["critical"]
        limit_warning = limits["warning"]
        diff = time.time() - lastRec.timestamp() 
        if diff > limit_critical:
            return _resolved(Status.CRITICAL, diff, "Arduino CRITICO")
        if diff > limit_warning:
            return _resolved(Status.WARNING, diff, "Arduino WARNING")
        return _resolved(Status.OK, diff, "Arduino OK")
    except Exception as e:
        log.error(f"[HEALTH] Error en _arduino_diagnose. {e}")
        return _resolved(Status.ERROR, 0, f"{e}")


# ------------------------------------------------------------------------------
# SECCIÓN: CONTROL RESULTADOS DE VERIFICACIóN SEGúN LA CONFIGURACIóN
# ------------------------------------------------------------------------------

# verificar_resultados_diagnosticos
def verify_diagnostic_results(config, call_detener_sistema):
    """
    Ejecuta los diagnósticos y detiene el sistema si hay fallas críticas.

    Args:
        config: Configuración del sistema.
        call_detener_sistema: Callback para detener el sistema.

    Returns:
        Status.CRITICAL si hubo falla grave, de lo contrario Status.OK.
    """
    hconfig = config["health_monitor_config"]
    url = f"{config["base_url"]}{hconfig["endpoint"]}"
    reporte = {
        "dispositivo_id": config.get("dispositivo_id"),
        "diagnostico": {
            "temp": _temperature_diagnose(hconfig["temp"]["limits"]),
            "disk": _disk_diagnose(hconfig["disk"]["limits"]),
            "power": _power_diagnose_controller(),
            "arduino": _arduino_diagnose(hconfig["arduino"]["limits"]),
        }
    }
    diag = reporte["diagnostico"]
    criticos = ["temp", "disk", "power"]
    hay_criticos = any(diag[k]["status"] in [Status.CRITICAL, Status.ERROR] for k in criticos)
    notify_status(reporte, url)
    if hay_criticos:
        log.critical(f"[HEALTH] Cierre de emergencia: {diag}")
        call_detener_sistema()
        return Status.CRITICAL
    log.info(f"[HEALTH] Dispositivo status: {diag}")
    return Status.OK

# notificar_status
def notify_status(reporte, url):
    """
    Envía un reporte de diagnóstico al servidor vía HTTP POST.

    Args:
        reporte: Diccionario con claves "dispositivo_id" y "diagnostico".
        url: Endpoint del servidor receptor del reporte.
    """
    try:
        payload = {
            "dispositivo_id": reporte["dispositivo_id"],
            "diagnostico": reporte["diagnostico"].copy()
        }
        for key in payload["diagnostico"]:
            estado_enum = payload["diagnostico"][key]["status"]
            payload["diagnostico"][key]["status"] = estado_enum.value
        requests.post(url, json=payload, timeout=5)
        log.info(f"[HEALTH] Reposte enviado al servidor: {payload}")
    except Exception as e:
        log.error(f"[HEALTH] No se pudo enviar el reporte al servidor: {e}")


# ------------------------------------------------------------------------------
# SECCIÓN: INICIO DEL SERVICIO EN HILO DIFERENTE SEGúN CONFIGURACIóN
# ------------------------------------------------------------------------------

def _core_loop(call_detener_sistema):
    """
    Bucle principal que ejecuta verificaciones periódicas del sistema.

    Args:
        call_detener_sistema: Función invocable para detener el sistema.
    """
    global general_next_time, power_next_time, _isRunning
    config = cargar_config()
    hconfig = config.get("health_monitor_config")
    g_interval = hconfig["inspection_interval_seg"]
    p_fast_interval = hconfig["power"]["fast_mode_interval_seg"]
    g_next = time.time() + 30       # espera 30s para iniciar
    p_next = time.time() + 30
    while _isRunning:
        now = time.time()
        if now >= g_next or now >= p_next:
            verify_diagnostic_results(config, call_detener_sistema)
            if now >= g_next:
                g_next += g_interval
            if now >= p_next:
                inter_power = p_fast_interval if power_is_fast_mode else g_interval
                p_next += inter_power
        next_event = min(g_next, p_next)
        diff = next_event - now
        sleep_time = max(0.5, min(5.0, diff))
        time.sleep(sleep_time)


# iniciar_diagnostico
def iniciar_diagnostico(call_detener_sistema):
    global _isRunning, _health_thread
    if not _isRunning:
        _isRunning = True
        _health_thread = threading.Thread(
            target=_core_loop,
            args=(call_detener_sistema,),
            daemon=True
        )
        _health_thread.start()
        log.info("[HEALTH] Servicio de diagnóstico iniciado.")



# detener_diagnostico
def detener_diagnostico():
    global _isRunning
    _isRunning = False
    log.info("[HEALTH] Servicio de diagnóstico detenido.")
