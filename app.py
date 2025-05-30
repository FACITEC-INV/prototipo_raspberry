from db_service import init_db, guardar_lectura
from sensor_service import leer_datos
from sync_service import iniciar_sincronizacion, detener_sincronizacion

def main():
    init_db()

    # Iniciar sincronizacion periodica en hilo aparte
    iniciar_sincronizacion()

    try:
        # Ejecutar lectura de datos (bloqueante)
        leer_datos(guardar_lectura)
    except KeyboardInterrupt:
        print("\n[SYSTEM] Deteniendo servicios...")
        detener_sincronizacion()

if __name__ == "__main__":
    main()
