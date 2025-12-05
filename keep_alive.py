from flask import Flask
from threading import Thread
import os

app = Flask(__name__)

@app.route('/')
def home():
    # Mensaje simple que el hosting revisa para saber que la app está viva.
    return "¡El Bot de Discord (Pollo Dinner) está Activo y Funciona Correctamente!"

def keep_alive():
    """Ejecuta el servidor Flask en un hilo separado para mantener el bot activo."""
    def run():
        # Usa el puerto de la variable de entorno 'PORT' proporcionada por el hosting, o 8080 por defecto.
        port = int(os.environ.get('PORT', 8080))
        app.run(host='0.0.0.0', port=port)

    t = Thread(target=run)
    t.start()