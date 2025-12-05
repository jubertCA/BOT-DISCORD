from flask import Flask
from threading import Thread
import os
import bot # Asegúrate de importar tu bot

# 1. Definición de la app de Flask (Necesario para Gunicorn)
app = Flask(__name__)

# 2. Rutas de Flask
@app.route('/')
def home():
    # Mensaje simple que el hosting revisa para saber que la app está viva.
    return "¡El Bot de Discord (Pollo Dinner) está Activo y Funciona Correctamente!"

# 3. Función para iniciar el bot de Discord (debe estar en un hilo)
def run_bot():
    # Asume que el objeto del cliente Discord en bot.py se llama 'client'
    bot.client.run(os.getenv("DISCORD_TOKEN"))

# 4. Iniciar el bot en el hilo secundario inmediatamente (Gunicorn gestiona el hilo principal)
t = Thread(target=run_bot)
t.start()