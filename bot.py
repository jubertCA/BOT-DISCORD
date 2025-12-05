import discord
from discord.ext import commands, tasks
from datetime import datetime, timedelta
import sqlite3
import os
import asyncio
from io import BytesIO
from PIL import Image, ImageDraw, ImageFont
from discord import app_commands
from dotenv import load_dotenv

# Importar keep_alive desde el módulo existente
from keep_alive import keep_alive # <--- Llama al servidor Flask

# Carga las variables del archivo .env
load_dotenv()

# --- CONFIGURACIÓN ---
TARGET_CHANNEL_ID = int(os.getenv(
    "TARGET_CHANNEL_ID",
    "1312183725450067968"))  # Canal donde se envían las imágenes (Pollos)
REPORT_CHANNEL_ID = int(os.getenv(
    "REPORT_CHANNEL_ID",
    "1304371409832906824"))  # Canal para el reporte mensual automático
DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
DB_NAME = "pollos_db.sqlite"
POLLO_EMOJI = "🍗"
# Las 5 reacciones automáticas (personalízalas si quieres)
REACTION_EMOJIS = [
    'peru:1433222611113873478', 'pubg35:1433193081670471780',
    'Pubg_Dance:1433193034165518377', 'Anime:1433193025017872414',
    'kurhe:1317814361103798332'
]

# Archivos para la generación de la imagen de reporte
BACKGROUND_IMAGE_PATH = "pubg_background.png"
FONT_PATH = "font.ttf"

# Configuración de Fuente (manejo de errores de archivo de fuente)
try:
    FONT_NORMAL = ImageFont.truetype(FONT_PATH, 45)
    FONT_TITLE = ImageFont.truetype(FONT_PATH, 60)
except Exception:
    FONT_NORMAL = ImageFont.load_default()
    FONT_TITLE = ImageFont.load_default()

# --- INICIALIZACIÓN DEL BOT Y BASE DE DATOS ---
intents = discord.Intents.default()
# CRUCIAL para on_message y revisar attachments
intents.message_content = True
intents.messages = True
intents.guilds = True
intents.members = True

bot = commands.Bot(command_prefix="!", intents=intents)


# --------------------------------------------------------------------------------
# --- FUNCIONES DE BASE DE DATOS ---
# --------------------------------------------------------------------------------
def init_db():
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS pollos (
            id INTEGER PRIMARY KEY,
            user_id INTEGER NOT NULL,
            username TEXT NOT NULL,
            guild_id INTEGER NOT NULL,
            count INTEGER NOT NULL,
            created_at TEXT NOT NULL
        )
    """)
    conn.commit()
    conn.close()


def add_pollo(user_id, username, guild_id):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    now = datetime.now().isoformat()
    cursor.execute(
        "INSERT INTO pollos (user_id, username, guild_id, count, created_at) VALUES (?, ?, ?, 1, ?)",
        (user_id, username, guild_id, now))
    conn.commit()
    conn.close()


def get_report(guild_id, start_date=None, end_date=None, user_id=None):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()

    query = "SELECT username, SUM(count) FROM pollos WHERE guild_id = ?"
    params = [guild_id]

    if user_id:
        query += " AND user_id = ?"
        params.append(user_id)

    if start_date:
        query += " AND created_at >= ?"
        params.append(start_date.isoformat())

    if end_date:
        end_date_inclusive = end_date + timedelta(days=1)
        query += " AND created_at < ?"
        params.append(end_date_inclusive.isoformat())

    query += " GROUP BY username ORDER BY SUM(count) DESC"

    cursor.execute(query, tuple(params))
    report = cursor.fetchall()
    conn.close()
    return report


def clear_old_data(month_to_clear):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()

    start_of_month = month_to_clear.strftime('%Y-%m-01')

    next_month = month_to_clear.replace(day=28) + timedelta(days=4)
    start_of_next_month = next_month.replace(day=1)

    cursor.execute(
        "DELETE FROM pollos WHERE created_at >= ? AND created_at < ?",
        (start_of_month, start_of_next_month.isoformat()))
    conn.commit()
    deleted_rows = cursor.rowcount
    conn.close()
    return deleted_rows


# --- FUNCIÓN DE GENERACIÓN DE IMAGEN ---
async def generate_report_image(title, report_data):

    def _generate():
        try:
            # Asume que tienes los archivos en la misma carpeta.
            img = Image.open(BACKGROUND_IMAGE_PATH).convert("RGB")
        except FileNotFoundError:
            # Crea una imagen de respaldo si no encuentra el fondo
            img = Image.new('RGB', (800, 600), color=(28, 28, 28))

        draw = ImageDraw.Draw(img)
        text_color = (255, 255, 255)

        # Título y Contenido
        title_text = f"🏆 {title.upper()} - POLLO DINNER REPORT 🏆"
        draw.text((40, 40), title_text, font=FONT_TITLE, fill=text_color)
        draw.text((40, 120), "RANK", font=FONT_NORMAL, fill=text_color)
        draw.text((150, 120), "MIEMBRO", font=FONT_NORMAL, fill=text_color)
        draw.text((650, 120), "POLLOS", font=FONT_TITLE, fill=text_color)

        y_start = 180
        for i, (username, count) in enumerate(report_data[:10]):
            rank = i + 1
            y_pos = y_start + (i * 75)

            rank_color = (255, 215, 0) if rank == 1 else (
                (192, 192, 192) if rank == 2 else
                ((205, 127, 50) if rank == 3 else text_color))

            draw.text((40, y_pos),
                      str(rank),
                      font=FONT_NORMAL,
                      fill=rank_color)
            draw.text((150, y_pos),
                      username,
                      font=FONT_NORMAL,
                      fill=text_color)
            draw.text((650, y_pos),
                      str(count),
                      font=FONT_NORMAL,
                      fill=text_color)

        buffer = BytesIO()
        img.save(buffer, format='PNG')
        buffer.seek(0)
        return discord.File(buffer, filename="pollos_reporte.png")

    try:
        return await bot.loop.run_in_executor(None, _generate)
    except Exception as e:
        print(f"Error al generar imagen: {e}")
        return None


# --------------------------------------------------------------------------------
# --- COMANDOS SLASH ---
# --------------------------------------------------------------------------------


@bot.tree.command(
    name="top_pollos",
    description=
    "Muestra el ranking de jugadores con más Pollos (Semanal, Mensual, Total)."
)
@discord.app_commands.describe(
    periodo='Selecciona el período: total, mensual o semanal')
@discord.app_commands.choices(periodo=[
    app_commands.Choice(name="Total Histórico", value="total"),
    app_commands.Choice(name="Mensual", value="mensual"),
    app_commands.Choice(name="Semanal", value="semanal")
])
async def pollo_top_cmd(interaction: discord.Interaction, periodo: str):
    await interaction.response.defer()
    now = datetime.now()
    start_date = None
    title = "TOP 10 Histórico de Pollos"
    if periodo == 'semanal':
        start_date = now - timedelta(weeks=1)
        title = "TOP 10 Semanal de Pollos"
    elif periodo == 'mensual':
        start_date = now.replace(day=1)
        title = "TOP 10 Mensual de Pollos"

    report_data = get_report(interaction.guild_id,
                             start_date=start_date,
                             end_date=now)

    if not report_data:
        return await interaction.followup.send(
            f"No se encontraron Pollos para el periodo **{periodo.upper()}**.")

    report_file = await generate_report_image(title, report_data)

    report_message = f"**👑 ¡{title.upper()}! 👑**\n\n"
    for i, (username, count) in enumerate(report_data[:10]):
        report_message += f"**#{i+1}:** {username} con **{count}** Pollos.\n"

    if report_file:
        await interaction.followup.send(report_message, file=report_file)
    else:
        await interaction.followup.send(report_message)


@bot.tree.command(
    name="mi_reporte",
    description="Muestra tu número total de Pollos o el de otro usuario.")
@discord.app_commands.describe(
    usuario='Miembro a revisar (opcional, por defecto es usted)')
async def mi_reporte_cmd(interaction: discord.Interaction,
                        usuario: discord.Member = None):
    await interaction.response.defer()
    user_to_report = usuario or interaction.user
    total_pollos = await bot.loop.run_in_executor(None, get_report,
                                                  interaction.guild_id, None,
                                                  None, user_to_report.id)
    count = total_pollos[0][1] if total_pollos else 0
    message = (
        f"🍗 **Reporte de Pollos para {user_to_report.display_name}** 🍗\n"
        f"El usuario **{user_to_report.display_name}** tiene un total de **{count}** pollos registrados."
    )
    await interaction.followup.send(message)


@bot.tree.command(
    name="admin_reset",
    description=
    "[Admin] Borra todos los registros de pollos. ¡Usar con cuidado!")
@app_commands.checks.has_permissions(manage_guild=True)
async def reset_command(interaction: discord.Interaction):
    await interaction.response.defer(ephemeral=True)

    def _reset_db():
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        cursor.execute("DELETE FROM pollos")
        conn.commit()
        conn.close()

    await bot.loop.run_in_executor(None, _reset_db)
    await interaction.followup.send(
        "✅ **¡Contador de pollos reiniciado a cero!**")


# --------------------------------------------------------------------------------
# --- EVENTOS Y TAREAS ---
# --------------------------------------------------------------------------------


@bot.event
async def on_ready():
    """Se ejecuta cuando el bot está conectado y listo."""
    init_db()
    print(f'Bot conectado como {bot.user}')

    try:
        synced = await bot.tree.sync()
        print(f"Sincronizados {len(synced)} comando(s) slash.")
    except Exception as e:
        print(f"Error al sincronizar comandos: {e}")

    if not monthly_report_task.is_running():
        # Llama a before_loop manualmente antes de iniciar la tarea
        await before_monthly_report_task()
        monthly_report_task.start()
        print("Tarea mensual iniciada.")


@bot.event
async def on_message(message):
    """
    Suma el Pollo a la base de datos y añade las 5 reacciones automáticas
    cuando se sube una imagen al canal de victorias.
    """
    # Ignora mensajes del propio bot
    if message.author == bot.user:
        return

    # Solo procesa en el canal configurado (TARGET_CHANNEL_ID)
    if message.channel.id == TARGET_CHANNEL_ID:

        # Verifica si el mensaje tiene adjuntos (attachments)
        if message.attachments:
            # Revisa si alguno de los adjuntos es una imagen
            is_image = any(attachment.content_type
                           and attachment.content_type.startswith('image/')
                           for attachment in message.attachments)

            if is_image:

                # 1. Añade el punto a la base de datos de forma asíncrona
                await bot.loop.run_in_executor(None, add_pollo,
                                               message.author.id,
                                               message.author.name,
                                               message.guild.id)
                print(
                    f"Pollo registrado automáticamente para {message.author.name} al subir imagen."
                )

                # 2. Añade las 5 reacciones automáticas
                try:
                    for emoji in REACTION_EMOJIS:
                        await message.add_reaction(emoji)

                    print(
                        f"5 reacciones añadidas a la imagen en canal {TARGET_CHANNEL_ID}."
                    )
                except Exception as e:
                    print(
                        f"No se pudo añadir una o más reacciones al mensaje: {e}"
                    )

    # NECESARIO: Procesa el mensaje para comandos slash/prefix
    await bot.process_commands(message)


# --------------------------------------------------------------------------------
# --- TAREAS PROGRAMADAS Y EJECUCIÓN ---
# --------------------------------------------------------------------------------
@tasks.loop(hours=24)
async def monthly_report_task():
    now = datetime.now()
    # Verifica si es el día 2 de cada mes
    if now.day == 2 and REPORT_CHANNEL_ID:

        last_month = now.replace(day=1) - timedelta(days=1)
        guild_id = bot.guilds[0].id if bot.guilds else None
        report_channel = bot.get_channel(REPORT_CHANNEL_ID)

        if guild_id and report_channel:
            # Obtener el reporte del mes pasado
            report_data = await bot.loop.run_in_executor(
                None, get_report, guild_id, last_month.replace(day=1),
                last_month, None)

            if report_data:
                month_name = last_month.strftime('%B %Y')
                report_title = f"🏆 TOP 10 POLLOS - REPORTE MENSUAL DE {month_name.upper()} 🏆"
                report_file = await generate_report_image(
                    report_title, report_data)

                report_message = f"**🍗 ¡REPORT DE POLLOS MENSUAL - {month_name}! 🍗**\n\n"
                for i, (username, count) in enumerate(report_data[:10]):
                    report_message += f"**#{i+1}:** {username} con **{count}** Pollos.\n"

                if report_file:
                    await report_channel.send(report_message, file=report_file)
                else:
                    await report_channel.send(report_message)
            else:
                await report_channel.send(
                    f"No se registraron Pollos en {last_month.strftime('%B %Y')}."
                )

        # Lógica de borrado de datos antiguos (2 meses atrás)
        if now.day == 2:
            two_months_ago = now.replace(day=1) - timedelta(days=1)
            two_months_ago = two_months_ago.replace(day=1) - timedelta(days=1)
            month_to_clear = two_months_ago.replace(day=1)

            # Borra datos de hace dos meses o más
            if (now - month_to_clear).days >= 58:
                deleted_count = await bot.loop.run_in_executor(
                    None, clear_old_data, month_to_clear.date())
                print(
                    f"Se borraron {deleted_count} registros de Pollos del mes de {month_to_clear.strftime('%B %Y')}."
                )


@monthly_report_task.before_loop
async def before_monthly_report_task():
    await bot.wait_until_ready()


if __name__ == "__main__":
    if DISCORD_TOKEN is None:
        print("ERROR: El token de Discord no está configurado.")
    elif TARGET_CHANNEL_ID == 0 or REPORT_CHANNEL_ID == 0:
        print(
            "ADVERTENCIA: Las IDs de canal (TARGET_CHANNEL_ID o REPORT_CHANNEL_ID) no están configuradas en .env o son 0."
        )
    else:
        try:
            # *CRUCIAL:* Inicia el servidor web en un hilo (keep_alive).
            keep_alive()
            print("Servidor web iniciado para mantener la conexión 24/7.")
            
            bot.run(DISCORD_TOKEN)
        except discord.errors.LoginFailure:
            print("ERROR: El token de Discord no es válido.")
        except Exception as e:
            print(f"ERROR: Fallo al iniciar el bot: {e}")