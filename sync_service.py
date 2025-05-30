import requests
from datetime import datetime, timedelta
from db_service import Lectura
import threading
from conf_service import cargar_config, guardar_config

timer = None
ultimo_intervalo = None

def obtener_info_sincronizacion(base_url, url_consulta, dispositivo_id):
    try:
        url = f"{base_url}{url_consulta}?dispositivo_id={dispositivo_id}"
        response = requests.get(url)
        if response.status_code == 200:
            data = response.json()
            timestamp = data.get("timestamp")
            nuevo_intervalo = int(data.get("intervalo_actualizacion", 1))
            return timestamp, nuevo_intervalo
        else:
            print(f"[ERROR] Consulta fallida: {response.status_code}")
    except Exception as e:
        print(f"[ERROR] No se pudo obtener informacion de sincronizacion: {e}")
    return None, 1

def filtrar_lecturas_desde(fecha_iso):
    if fecha_iso:
        try:
            fecha = datetime.fromisoformat(fecha_iso)
            return Lectura.select().where(Lectura.timestamp > fecha).order_by(Lectura.timestamp)
        except ValueError:
            print("[WARN] Timestamp invalido. Enviando todas las lecturas.")
    return Lectura.select().order_by(Lectura.timestamp)

def enviar_lecturas(base_url, url_envio, dispositivo_id, lecturas):
    payload = []
    for l in lecturas:
        payload.append({
            "id": str(l.id),
            "dispositivo_id": dispositivo_id,
            "timestamp": l.timestamp.isoformat() if l.timestamp else None,
            "od": l.od,
            "ph": l.ph,
            "con": l.con,
            "tur": l.tur,
            "tsd": l.tsd,
            "tem": l.tem
        })

    if not payload:
        print("[SYNC] No hay lecturas nuevas para enviar.")
        return

    try:
        url = f"{base_url}{url_envio}"
        response = requests.post(url, json=payload)
        if response.status_code == 200:
            print(f"[SYNC] Se enviaron {len(payload)} lecturas.")
        else:
            print(f"[ERROR] Fallo el envio: {response.status_code} - {response.text}")
    except Exception as e:
        print(f"[ERROR] Error al enviar lecturas: {e}")

def eliminar_lecturas_antiguas(dias=30):
    try:
        dias = int(dias)
    except (ValueError, TypeError):
        dias = 30
    limite_fecha = datetime.now() - timedelta(days=dias)
    query = Lectura.delete().where(Lectura.timestamp < limite_fecha)
    eliminados = query.execute()
    print(f"[SYNC] Se eliminaron {eliminados} lecturas con mas de {dias} dias.")

def tarea_periodica():
    global timer, ultimo_intervalo

    config = cargar_config()
    base_url = config["base_url"]
    url_consulta = config["url_consulta"]
    url_envio = config["url_envio"]
    dispositivo_id = config["dispositivo_id"]
    dias_retencion = config.get("dias_retencion_local", 30)

    # Obtener timestamp de la ultima lectura y nuevo intervalo
    ultimo_ts, nuevo_intervalo = obtener_info_sincronizacion(base_url, url_consulta, dispositivo_id)

    if nuevo_intervalo != config.get("intervalo_actualizacion"):
        config["intervalo_actualizacion"] = nuevo_intervalo
        guardar_config(config)
        print(f"[SYNC] Intervalo actualizado a {nuevo_intervalo} minutos.")

    # Enviar lecturas nuevas
    lecturas = filtrar_lecturas_desde(ultimo_ts)
    enviar_lecturas(base_url, url_envio, dispositivo_id, lecturas)

    eliminar_lecturas_antiguas(dias_retencion)

    # Cancelar y reprogramar el temporizador si cambia el intervalo
    if timer and ultimo_intervalo != nuevo_intervalo:
        timer.cancel()
        print("[SYNC] Timer anterior cancelado por cambio de intervalo.")

    ultimo_intervalo = nuevo_intervalo
    tiempo_espera = nuevo_intervalo * 60
    timer = threading.Timer(tiempo_espera, tarea_periodica)
    timer.start()

def iniciar_sincronizacion():
    tarea_periodica()

def detener_sincronizacion():
    global timer
    if timer:
        timer.cancel()
