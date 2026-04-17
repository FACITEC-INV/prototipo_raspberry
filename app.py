import time
from logs_service import log
from db_service import init_db, guardar_lectura, iniciar_mantenimiento, detener_mantenimiento
from sensor_service import iniciar_lectura, detener_lectura
from sync_service import iniciar_sincronizacion, detener_sincronizacion

def main():
    log.info("[MAIN] === Iniciando Sistema de Monitoreo FACITEC ===")

    init_db()

    log.info("[MAIN] Iniciando servicio de sensores...")
    iniciar_lectura(guardar_lectura)

    log.info("[MAIN] Iniciando servicio de mantenimiento...")
    iniciar_mantenimiento()

    log.info("[MAIN] Iniciando servicio de sincronización...")
    iniciar_sincronizacion()

    try:
        log.info("[MAIN] Todos los servicios activos. Presione Ctrl+C para salir.")
        # Mantiene vivo el proceso principal
        while True:
            time.sleep(3)

    except KeyboardInterrupt:
        log.warning("[MAIN] Deteniendo servicios...")

    finally:
        detener_lectura()
        detener_mantenimiento()
        detener_sincronizacion()
        log.info("[MAIN] Sistema cerrado correctamente.")

if __name__ == "__main__":
    main()
