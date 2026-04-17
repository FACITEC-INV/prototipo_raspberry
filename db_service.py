import threading
from peewee import Model, SqliteDatabase, BooleanField, FloatField, DateTimeField, UUIDField
from datetime import datetime, timedelta
from uuid import uuid4
from logs_service import log
from conf_service import cargar_config

# ------------------------------------------------------------------------------
# SECCIÓN: CONFIGURACIÓN DE LA BASE DE DATOS
# ------------------------------------------------------------------------------

db = SqliteDatabase(
        'sensores.db',
        pragmas={
            'journal_mode': 'wal',          # Activa el modo WAL para concurrencia
            'cache_size': -1024 * 128,      # 128MB de caché para mejorar velocidad
            'foreign_keys': 1,              # Enforce integridad referencial
            'ignore_check_constraints': 0,
            'synchronous': 1                # Modo Normal, recomendado para WAL
        }
     )

# ------------------------------------------------------------------------------
# SECCIÓN: MODELOS
# ------------------------------------------------------------------------------

class BaseModel(Model):
    class Meta:
        database = db

class Lectura(BaseModel):
    """ Modelo para la base de datos """
    id = UUIDField(primary_key=True, default=uuid4)
    timestamp = DateTimeField(default=datetime.now)
    od = FloatField(null=True)
    ph = FloatField(null=True)
    con = FloatField(null=True)
    tur = FloatField(null=True)
    tsd = FloatField(null=True)
    tem = FloatField(null=True)
    is_send=BooleanField(null=False, default=False)

# ------------------------------------------------------------------------------
# SECCIÓN: OPERACIONES CRUD
# ------------------------------------------------------------------------------

def init_db():
    with db:
        db.create_tables([Lectura], safe=True)
        log.info("[DBSERVICE] Base de datos iniciada.")

def guardar_lectura(data):
    """
    Persiste una nueva lectura de sensores en la base de datos local.
    
    Args:
        data (dict): Diccionario que contiene los valores de los sensores 
                     (ph, od, con, tur, tsd, tem). Las llaves deben coincidir 
                     con los nombres de los campos del modelo Lectura.

    Returns:
        Lectura: La instancia del objeto creado con su ID (UUID) y timestamp generados.
    """
    with db.atomic():
        return Lectura.create(**data)

 
def actualizar_enviados(lista_ids):
    """Actualiza el is_send a True para los registros confirmados.

    Args:
        lista_ids (list): Lista de IDs (UUID o Integer) recuperados de la DB.

    Returns:
        int: Cantidad de registros actualizados exitosamente.

    Raises:
        En caso de falla envía 0
    """
    if not lista_ids: return 0

    with db.atomic():
        try:
            query = Lectura.update(is_send=True).where(Lectura.id << lista_ids)
            filas_afectadas = query.execute()
            log.info(f"[DBSERVICE] {filas_afectadas} registros marcados como enviados.")
            return filas_afectadas

        except Exception as e:
            log.error(f"[DBSERVICE] Error al actualizar los registros: {e}")
            return 0

def obtener_pendientes():
    """ 
    Obtiene todas las lecturas con estado is_send False. 

    Returns:
        Lectura (list): Lista de las lecturas pendientes de ser enviadas

    Raises: 
        En caso de cualquier error se envía una lista vacía
    """
    with db:
        try:
            return list(
                    Lectura.select()
                    .where(Lectura.is_send==False)
                    .order_by(Lectura.timestamp.asc())
                    .limit(1000)
                    .dicts()
                )

        except Exception as e:
            log.error(f"[DBSERVICE] Error al recuperar pendientes: {e}")
            return []

def eliminar_lecturas_antiguas(dias=30):
    """
    Realiza la limpieza de registros antiguos para optimizar espacio en disco.
    Solo debe invocarse después de asegurar que los datos han sido sincronizados.

    Args:
        dias: Días de retención.
    """
    try:
        limite_fecha = datetime.now() - timedelta(days=int(dias))
        query = Lectura.delete().where(
            (Lectura.timestamp < limite_fecha) & (Lectura.is_send == True)
        )
        eliminados = query.execute()
        if eliminados > 0:
            log.info(f"[DBSERVICE] Se eliminaron {eliminados} registros antiguos.")

    except Exception as e:
        log.error(f"[DBSERVICE] Error al eliminar registros antiguos.")

# ------------------------------------------------------------------------------
# SECCIÓN: HILO DE MANTENIMIENTO
# ------------------------------------------------------------------------------

_mantenimiento_timer = None

def _tarea_mantenimiento():
    """
    Ejecuta el bucle infinito de limpieza programada de la base de datos.
    
    Recupera la configuración de retención en cada ciclo para permitir 
    cambios dinámicos, ejecuta la eliminación de registros antiguos y entra en 
    estado de reposo durante 24 horas.
    """
    global _mantenimiento_timer

    try:
        log.info("[DBSERVICE] Iniciando limpieza de base de datos...")
        dias = cargar_config().get("dias_retencion_local", 30)
        eliminar_lecturas_antiguas(dias)

    except Exception as e:
        log.error(f"[DBSERVICE] Error en el servicio de mantenimiento: {e}")

    # Programar el timer para dentro de 24 horas (86400 segundos)
    _mantenimiento_timer = threading.Timer(86400, _tarea_mantenimiento)
    _mantenimiento_timer.daemon = True
    _mantenimiento_timer.start()

def iniciar_mantenimiento():
    """Inicializa el hilo de mantenimiento de la base de datos."""
    log.info("[DBSERVICE] Servicio de mantenimiento iniciado.")
    _tarea_mantenimiento()

def detener_mantenimiento():
    """
    Detiene el ciclo de mantenimiento de forma segura.
    """
    global _mantenimiento_timer
    if _mantenimiento_timer:
        _mantenimiento_timer.cancel()
        log.info("[DBSERVICE] Servicio de mantenimiento finalizado")
