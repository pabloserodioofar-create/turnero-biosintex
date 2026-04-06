# Turnero Biosintex

Sistema de gestión de turnos para proveedores de Biosintex.

## Funcionalidades

- **Login de proveedores**: Ingreso con número de proveedor y contraseña
- **Reservar turnos**: Los proveedores reservan turnos según disponibilidad
- **Validación por presupuesto**: Los turnos se limitan según el mes de entrega de la OC (columna Q)
- **Panel supervisor**: Calendario de turnos, bloqueo de días, gestión de proveedores
- **Actualización de datos**: Subida de archivo Excel con órdenes de compra

## Requisitos

- Python 3.8+
- Flask
- Flask-Login
- Flask-SQLAlchemy
- Pandas
- OpenPyXL

## Instalación

```bash
# Clonar el repositorio
git clone <repo-url>
cd turnero-biosintex

# Crear entorno virtual
python -m venv venv
source venv/bin/activate  # En Windows: venv\Scripts\activate

# Instalar dependencias
pip install flask flask-login flask-sqlalchemy pandas openpyxl

# Ejecutar
python app.py
```

## Uso

1. **Supervisor**: Acceder a `http://localhost:5000/login`
   - Usuario: `admin@biosintex.com`
   - Contraseña: `admin123`

2. **Proveedores**: Se crean automáticamente desde el archivo Excel
   - Los nuevos proveedores reciben contraseña al iniciar la app
   - La primera vez deben completar email y teléfono

## Archivo de Turnos

El archivo `Turnos.xlsx` debe tener:
- **Hoja1**: Órdenes de compra con columnas:
  - Orden de Compra
  - Proveedor
  - Fecha Entrega (Columna Q)
  - Lugar de Recepción
  - Artículo
  - Cantidad Pendiente

El supervisor puede actualizar este archivo desde el panel.

## Despliegue en Railway

1. Crear cuenta en [Railway](https://railway.app)
2. Conectar repositorio de GitHub
3. Agregar variable de entorno: `FLASK_ENV=production`
4. Desplegar

## Notas

- La base de datos (proveedores y turnos) se guarda en `instance/turneros_v2.db`
- Los nuevos proveedores se crean automáticamente al iniciar o subir Excel
- Los turnos se limitan al mes de entrega de la OC (presupuesto)
