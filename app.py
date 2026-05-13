import time
from logs_service import log
from db_service import init_db, guardar_lectura, iniciar_mantenimiento, detener_mantenimiento
from sensor_service import iniciar_lectura, detener_lectura
from sync_service import iniciar_sincronizacion, detener_sincronizacion
from health_service import iniciar_diagnostico, detener_diagnostico

app_is_running = False

def main():
    global app_is_running
    try:
        log.info("[MAIN] === Iniciando Sistema de Monitoreo FACITEC ===")
        init_db()
        log.info("[MAIN] Iniciando servicio de sensores...")
        iniciar_lectura(guardar_lectura)
        log.info("[MAIN] Iniciando servicio de mantenimiento...")
        iniciar_mantenimiento()
        log.info("[MAIN] Iniciando servicio de sincronización...")
        iniciar_sincronizacion()
        log.info("[MAIN] Iniciando servicio de diagnóstico...")
        iniciar_diagnostico(detener_sistema)
        log.info("[MAIN] Todos los servicios activos. Presione Ctrl+C para salir.")
        app_is_running = True
        # Mantiene vivo el proceso principal
        while app_is_running:
            time.sleep(3)
    except KeyboardInterrupt:
        log.warning("[MAIN] Deteniendo servicios...")
        detener_sistema()
    except Exception as e:
        log.error(f"[MAIN] Error no controlado en el hilo principal: {e}")
        detener_sistema()


def detener_sistema():
    global app_is_running
    log.info("[MAIN] Iniciando secuencia de apagado.")
    detener_lectura()
    detener_mantenimiento()
    detener_sincronizacion()
    detener_diagnostico()
    app_is_running = False


if __name__ == "__main__":
    main()

