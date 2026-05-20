![Banner del Proyecto](https://drive.usercontent.google.com/download?id=1hFPIja3MBeFldDc1G6xueYSvr-Ts9fp-)

# Prototipo de dispositivo de captura de datos para monitoreo de calidad del agua

Este proyecto contiene el código fuente para el dispositivo de captura de datos de parámetros de calidad de agua para un sistema de monitoreo de la calidad del agua de ríos, enmarcado en el proyecto de investigación [**PINV01-267**](https://sca.facitec.edu.py/proyecto), financiado por el **CONACYT** de Paraguay a través de la **FACITEC - UNICAN**.

### Estructura del proyecto

```text
 ├── app.py                # Orquestador principal del sistema
 ├── app.service           # Archivo de configuración para el servicio systemd
 ├── conf_service.py       # Servicio de gestión de configuración local (JSON)
 ├── config.json           # Parámetros de configuración (URLs, IDs, intervalos, límites)
 ├── db_service.py         # Gestión de base de datos SQLite, mantenimiento y limpieza
 ├── health_service.py     # Servicio de autodiagnóstico de hardware y resiliencia energética
 ├── logs_service.py       # Configuración del sistema de logging rotativo
 ├── README.md             # Documentación técnica del proyecto
 ├── LICENSE.md            # Licencia del proyecto
 ├── requirements.txt      # Dependencias del proyecto
 ├── sensor_service.py     # Lógica de comunicación serial y captura de sensores
 └── sync_service.py       # Orquestador de sincronización y envío de datos

```

## Arquitectura del software

### Flujo general de datos

Este diagrama describe el trayecto de la información desde el entorno físico hasta el almacenamiento centralizado, incorporando la supervisión del estado del hardware.

```mermaid
graph LR
    subgraph "Entorno Físico"
        A[Sensores]
    end
    
    subgraph "Captura y Control"
        B[Arduino]
    end

    subgraph "Procesamiento y Diagnóstico (Raspberry Pi)"
        C[(Base de Datos Local)]
        E[Health_Service]
    end

    subgraph "Nube / Remoto"
        D[Servidor Central / API]
    end

    A -- "Señal Analógica/Digital" --> B
    B -- "Puerto Serial (USB)" --> C
    C -- "Protocolo HTTP (JSON)" --> D
    E -- "Reporte de Estado HTTP (JSON)" --> D

```

### Componentes de software

El sistema está diseñado bajo una arquitectura de **multihilo (Multithreading)**, permitiendo que cada servicio opere de forma independiente sin bloquear al resto del sistema. El módulo de salud actúa como un supervisor crítico sobre el orquestador principal.

```mermaid
graph TD
    subgraph "Raspberry Pi (SCA)"
        S[Sensor_Service]
        DBS[DB_Service]
        SYN[Sync_Service]
        HLT[Health_Service]
        DB[(sensores.db)]
        LOG[sistema.log]
    end

    USB[Puerto Serial / Arduino] --> S
    S -- "Envia lecturas" --> DBS
    DBS -- "Guarda lecturas" --> DB
    S -- "Registrar eventos" --> LOG
    
    DBS -- "Limpieza y WAL" --> DB
    DBS -- "Registrar eventos" --> LOG
    
    SYN -- "Consultar Pendientes" --> DBS
    DBS -- "Devuelve pendientes" --> SYN
    SYN -- "Handshake / Envío POST" --> API[Servidor HTTP Externo]
    API -- "Respuesta / Intervalos" --> SYN
    SYN -- "Pasa id de enviados" --> DBS
    DBS -- "Marcar como Enviado" --> DB
    SYN -- "Registrar eventos" --> LOG

    HLT -- "Monitorea SoC, SD, Energía, DB" --> HLT
    HLT -- "Envía reporte HTTP POST" --> API
    HLT -- "Falla crítica: Cierre de Emergencia (Exit 0)" --> app[app.py]

```

* **Sensor service:** Mantiene una comunicación serial persistente con el Arduino. Está diseñado para evitar reinicios constantes del microcontrolador, garantizando la estabilidad térmica de los sensores.
* **Db service:** Gestiona la persistencia en una base de datos SQLite optimizada con el modo **WAL (Write-Ahead Logging)** para permitir lecturas y escrituras simultáneas. Incluye un hilo de mantenimiento para limpieza automática de datos antiguos.
* **Sync service:** Realiza un *handshake* dinámico con el servidor para actualizar intervalos de captura y gestiona el envío de lotes pendientes cuando hay conectividad.
* **Health service:** Hilo supervisor independiente que monitorea activamente la temperatura del SoC de la Raspberry Pi, el almacenamiento en la tarjeta SD, el estado del lazo con el Arduino y los flags de subvoltaje de la línea de energía mediante comandos internos del sistema.

## Requisitos de hardware

El prototipo se integra mediante los siguientes componentes:

* **Orquestador:** Raspberry Pi 4 Model B (o similar).
* **Controlador de sensores:** Arduino Nano / Uno.
* **Sensores integrados:**
* Oxígeno disuelto (OD).
* Potencial de hidrógeno (pH).
* Conductividad eléctrica.
* Turbidez.
* Sólidos disueltos totales (TDS).
* Temperatura del agua.

* **Interfaz:** Conexión Serial vía USB con protocolo de reconexión automática.

## Requisitos de software y dependencias

| Software / Librería | Descripción |
| --- | --- |
| **Python 3.13.5+** | Lenguaje base de ejecución. |
| **peewee** | ORM ligero para gestión de SQLite. |
| **pyserial** | Comunicación con el hardware Arduino. |
| **requests** | Cliente HTTP para sincronización con la API central y reportes de salud. |
| **venv** | Entorno virtual para aislamiento de dependencias. |

## Instalación y configuración

1. **Clonar el repositorio:**

```bash
git clone https://github.com/FACITEC-INV/prototipo_raspberry.git
cd prototipo_raspberry

```

2. **Configurar el entorno virtual:**

```bash
python3 -m venv env
source env/bin/activate
pip install -r requirements.txt

```

3.  **Configuración (`config.json`):**
    Ajustar los parámetros según el servidor de destino y los umbrales físicos del nodo:

```json
{
  "device_name": "nodo-rio-piratiy",
  "base_url": "[http://192.168.0.243:8080/api](http://192.168.0.243:8080/api)",
  "url_consulta": "/sync",
  "url_envio": "/lecturas/add",
  "dispositivo_id": "22f8dbe0-9324-4798-b3b3-38ccdf200d2d",
  "intervalo_actualizacion_min": 10,
  "dias_retencion_local": 30,
  "intervalo_lectura_seg": 180,
  "health_monitor_config": {
    "endpoint": "/sync/status",
    "temp": {
      "limits": { "warning": 60, "critical": 75 }
    },
    "disk": {
      "limits": { "warning": 10, "critical": 5 }
    },
    "power": {
      "fast_mode_interval_seg": 40
    },
    "arduino": {
      "limits": { "warning": 600, "critical": 900 },
      "comment": "Limites: tiempo en segundos del ultimo registro en DB"
    },
    "inspection_interval_seg": 900
  }
}
```

## Gestión de ejecución (Systemd)

Para garantizar que el SCA inicie automáticamente al encender la Raspberry Pi y maneje los cierres por seguridad de manera inteligente:

1. **Instalar el servicio:**

```bash
sudo cp app.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable app.service
sudo systemctl start app.service
```

2. **Configuración del ciclo de vida (`app.service`):**
El servicio utiliza la política `Restart=on-failure`. Si el script de salud detecta una falla crítica de hardware o energía, ejecutará un cierre de emergencia controlado de todos los hilos, devolviendo un código de salida `0` (éxito). **Systemd** interpretará esta salida limpia como una detención intencional y mantendrá el proceso inactivo, protegiendo al hardware de reinicios cíclicos en condiciones inestables.
3. **Comandos útiles de monitoreo:**

```bash
# Ver estado del servicio
sudo systemctl status app.service
# Ver logs en tiempo real
journalctl -u app.service -f
```

## Estructura de datos (Base de datos)

El sistema utiliza **UUID** como clave primaria para garantizar la unicidad de los registros entre múltiples dispositivos durante la sincronización global con la API central.

### Diccionario de datos: Tabla `Lectura`

| Campo | Tipo | Descripción |
| --- | --- | --- |
| `id` | UUID | Identificador único universal (Primary Key). |
| `timestamp` | DateTime | Fecha y hora local de la captura. |
| `od` | Float | Oxígeno disuelto (mg/L). |
| `ph` | Float | Potencial de hidrógeno. |
| `con` | Float | Conductividad eléctrica (µS/cm). |
| `tur` | Float | Turbidez (NTU). |
| `tsd` | Float | Sólidos disueltos totales (ppm). |
| `tem` | Float | Temperatura del agua (°C). |
| `is_send` | Boolean | Estado de sincronización (True: Enviado / False: Pendiente). |

## Manejo de errores y resiliencia

El SCA implementa un diseño **Self-healing** (auto-recuperable) y enfocado en la mitigación de daños físicos:

* **Falta de internet:** Si el servidor no está disponible, las lecturas se acumulan localmente y se envían automáticamente en lotes una vez se restablece la conexión.
* **Desconexión de hardware:** El servicio de sensores detecta la pérdida de comunicación con el Arduino e intenta reconectar de forma automática sin detener la aplicación.
* **Protección ante caídas de tensión y sobrecalentamiento:** Al detectarse anomalías críticas continuas (como subvoltajes acumulados por baja carga en la batería del panel solar o temperaturas extremas en el SoC), el `Health_Service` comanda un apagado ordenado. Cierra de forma segura las conexiones a la base de datos para evitar la corrupción de la tarjeta SD y finaliza la ejecución de forma limpia. El dispositivo permanecerá ocioso consumiendo el mínimo de energía posible hasta el corte total por descarga o hasta que la radiación solar recupere la batería y provoque un reinicio por hardware limpio.

## Autores y contacto

* **Investigador principal:** Daniel Romero
* **Director del proyecto:** Rodrigo Martínez
* **Equipo de desarrollo:** David Ruiz Diaz, Nazario Ayala, Angel Heimann, Gloria Ortiz.
* **Contacto:** [dir.invext@facitec.edu.py]()
* **Institución:** Facultad de Ciencias y Tecnología (FACITEC) - Universidad Nacional de Canindeyú (UNICAN).

## Licencia

Este proyecto está licenciado bajo los términos de la **Licencia Pública General de GNU v3.0**. Consulta el archivo [LICENSE.md](https://www.google.com/search?q=./LICENSE.md) para más detalles.
