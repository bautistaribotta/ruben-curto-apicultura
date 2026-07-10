## Instalación y Configuración Local

Asegúrese de tener instalado Python 3.10+ y un servidor MySQL ejecutándose localmente.

**1. Clonar el repositorio**

```bash
git clone <https://github.com/bautistaribotta/southern_honey_group.git>
cd southern_honey_group

```

**2. Crear y activar el entorno virtual**

```bash
python -m venv venv

# En Linux/macOS:
source venv/bin/activate

# En Windows:
venv\Scripts\activate

```

**3. Instalar las dependencias**

```bash
pip install -r requirements.txt

```

**4. Configurar las variables de entorno**
Cree un archivo `.env` en la raíz del proyecto (al mismo nivel que `manage.py`) con las siguientes credenciales para conectar su base de datos local y asegurar el proyecto:

```env
SECRET_KEY=ingrese_su_secret_key_aqui
DB_NAME=nombre_de_su_base_de_datos
DB_USER=su_usuario_mysql
DB_PASSWORD=su_contraseña_mysql
DB_HOST=localhost
DB_PORT=3306

```

**5. Ejecutar migraciones**

```bash
python manage.py makemigrations
python manage.py migrate

```

**6. Crear un superusuario (opcional pero recomendado)**

```bash
python manage.py createsuperuser

```

**7. Iniciar el servidor de desarrollo**

```bash
python manage.py runserver

```

El software estará disponible de forma local ingresando a `http://127.0.0.1:8000/`.

---
