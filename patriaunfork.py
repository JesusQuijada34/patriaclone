import telebot
from telebot import types
import os
import json
import re
import requests
import socket
import threading
import time
import signal
import sys

# --- CONFIGURACIÓN DE ACCESO Y CONTROL ---
CONFIG_FILE = "patriaunfork.json"
LEAKS_FILE = "leaks.json"

# IDs de usuarios que pueden ignorar la verificación de grupo/canal (separados por coma)
IGNORAR_VERIFICACION_IDS = [int(x) for x in os.environ.get("IGNORAR_VERIFICACION_IDS", "").split(",") if x.strip().isdigit()]

# IDs y user/links de grupo/canal requeridos
CANAL_ID = -100
GRUPO_ID = -100
CANAL_USERNAME = ""
GRUPO_USERNAME = ""
CANAL_LINK = f"https://t.me/{CANAL_USERNAME}"
GRUPO_LINK = f"https://t.me/{GRUPO_USERNAME}"

# Para banear usuarios (guardar en archivo para persistencia)
BANEADOS_FILE = "userbanned.json"
def cargar_baneados():
    if os.path.exists(BANEADOS_FILE):
        with open(BANEADOS_FILE, "r") as f:
            return set(json.load(f))
    return set()
def guardar_baneados(baneados):
    with open(BANEADOS_FILE, "w") as f:
        json.dump(list(baneados), f, indent=4)
baneados = cargar_baneados()

def cargar_config():
    if not os.path.exists(CONFIG_FILE):
        token = input("Introduce el token de tu bot de Telegram: ")
        config = {"TELEGRAM_TOKEN": token, "usuarios": {}}
        with open(CONFIG_FILE, "w") as f:
            json.dump(config, f, indent=4)
        return config
    else:
        with open(CONFIG_FILE, "r") as f:
            return json.load(f)

def guardar_config(config):
    with open(CONFIG_FILE, "w") as f:
        json.dump(config, f, indent=4)

def guardar_leak(leak_data):
    if os.path.exists(LEAKS_FILE):
        with open(LEAKS_FILE, "r") as f:
            leaks = json.load(f)
    else:
        leaks = []
    leaks.append(leak_data)
    with open(LEAKS_FILE, "w") as f:
        json.dump(leaks, f, indent=4)

config = cargar_config()
TELEGRAM_TOKEN = config.get("TELEGRAM_TOKEN", "TU_TOKEN_AQUI")
bot = telebot.TeleBot(TELEGRAM_TOKEN, parse_mode="Markdown")

# --- FUNCIONES DE VERIFICACIÓN DE USUARIO EN GRUPO Y CANAL ---

def es_ignorado(user_id):
    return int(user_id) in IGNORAR_VERIFICACION_IDS

def es_baneado(user_id):
    return int(user_id) in baneados

def banear_usuario(user_id):
    baneados.add(int(user_id))
    guardar_baneados(baneados)

def verificar_enlace(user_id):
    # Devuelve True si el usuario está en el grupo Y canal, o está en la lista de ignorados
    if es_ignorado(user_id):
        return True
    try:
        canal_status = bot.get_chat_member(CANAL_ID, user_id)
        grupo_status = bot.get_chat_member(GRUPO_ID, user_id)
        # Solo si no está baneado y es miembro (no kicked ni left)
        if (canal_status.status in ["member", "administrator", "creator"]) and (grupo_status.status in ["member", "administrator", "creator"]):
            return True
    except Exception as e:
        print(f"Error verificando enlace: {e}")
    return False

def mensaje_verificacion():
    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.add(
        types.InlineKeyboardButton("Unirme al Canal", url=CANAL_LINK),
        types.InlineKeyboardButton("Unirme al Grupo", url=GRUPO_LINK),
    )
    markup.add(types.InlineKeyboardButton("✅ Ya me uní, verificar", callback_data="verificar_union"))
    return markup

def acceso_requerido(func):
    # Decorador para comandos: solo permite si está verificado
    def wrapper(message, *args, **kwargs):
        user_id = message.from_user.id
        if es_baneado(user_id):
            bot.send_message(message.chat.id, "🚫 Has sido baneado del bot, grupo y canal.")
            return
        if not verificar_enlace(user_id):
            bot.send_message(
                message.chat.id,
                f"🚨 *Debes unirte al canal y grupo para usar el bot.*\n\n"
                f"👉 [Canal]({CANAL_LINK})\n"
                f"👉 [Grupo]({GRUPO_LINK})\n\n"
                "Una vez te unas, pulsa el botón para verificar.",
                reply_markup=mensaje_verificacion(),
                parse_mode="Markdown"
            )
            return
        return func(message, *args, **kwargs)
    return wrapper

# --- UTILIDADES DE LEAKS Y OSINT ---

def extraer_userpass(texto):
    patron = re.compile(r'([a-zA-Z0-9_.-]+)[\s:|]+([a-zA-Z0-9@#_.\-!$%&*]+)')
    return list(set(patron.findall(texto)))

def extraer_urls(texto, palabra=None):
    url_pat = re.compile(r'https?://[^\s\'"<>]+')
    urls = set(url_pat.findall(texto))
    if palabra:
        urls = {u for u in urls if palabra.lower() in u.lower()}
    return list(urls)

def quitar_lineas_repetidas(texto):
    lineas = texto.splitlines()
    return "\n".join(sorted(set([l.strip() for l in lineas if l.strip()])))

def buscar_github(query, max_resultados=10):
    headers = {"Accept": "application/vnd.github.v3.text-match+json"}
    url = f"https://api.github.com/search/code?q={requests.utils.quote(query)}"
    try:
        r = requests.get(url, headers=headers, timeout=10)
        if r.status_code == 200:
            items = r.json().get("items", [])[:max_resultados]
            resultados = []
            for item in items:
                resultados.append(f"{item['html_url']}")
            return resultados
        else:
            return []
    except Exception:
        return []

def buscar_js_endpoints(url):
    try:
        r = requests.get(url, timeout=10)
        js_urls = re.findall(r'<script[^>]+src="([^"]+\.js)"', r.text)
        endpoints = set()
        for js_url in js_urls:
            if not js_url.startswith("http"):
                js_url = requests.compat.urljoin(url, js_url)
            try:
                js_code = requests.get(js_url, timeout=7).text
                endpoints.update(re.findall(r'https?://[^\s\'"<>]+', js_code))
            except Exception:
                continue
        return list(endpoints)
    except Exception:
        return []

def buscar_subdominios(domain):
    try:
        r = requests.get(f"https://crt.sh/?q=%25.{domain}&output=json", timeout=10)
        subdominios = set()
        if r.status_code == 200:
            for entry in r.json():
                name = entry.get("name_value", "")
                for sub in name.split("\n"):
                    subdominios.add(sub.strip())
        vivos = []
        for sub in sorted(subdominios):
            try:
                ip = socket.gethostbyname(sub)
                vivos.append(f"{sub} ({ip})")
            except Exception:
                continue
        return vivos
    except Exception:
        return []

def buscar_dni_databreach(dni):
    if not os.path.exists(LEAKS_FILE):
        return []
    with open(LEAKS_FILE, "r") as f:
        leaks = json.load(f)
    resultados = []
    for leak in leaks:
        if isinstance(leak, dict):
            texto = json.dumps(leak)
        else:
            texto = str(leak)
        if dni in texto:
            resultados.append(texto)
    return resultados

def informe_completo_dni(dni):
    informe = f"🕵️ *Informe OSINT para DNI:* `{dni}`\n"
    leaks = buscar_dni_databreach(dni)
    if leaks:
        informe += f"🔎 *Encontrado en {len(leaks)} leaks locales:*\n"
        for l in leaks[:5]:
            informe += f"- `{l[:200]}`\n"
    else:
        informe += "❌ *No encontrado en leaks locales.*\n"
    return informe

def buscar_titular_telefono(telefono):
    if not os.path.exists(LEAKS_FILE):
        return []
    with open(LEAKS_FILE, "r") as f:
        leaks = json.load(f)
    resultados = []
    for leak in leaks:
        if telefono in str(leak):
            resultados.append(leak)
    return resultados

def ficha_estafador(dni=None, telefono=None):
    ficha = ""
    if dni:
        ficha += informe_completo_dni(dni)
    if telefono:
        resultados = buscar_titular_telefono(telefono)
        if resultados:
            ficha += f"\n📞 *Teléfono* `{telefono}` *encontrado en {len(resultados)} leaks:*\n"
            for l in resultados[:5]:
                ficha += f"- `{str(l)[:200]}`\n"
        else:
            ficha += f"\n❌ *Teléfono* `{telefono}` *no encontrado en leaks locales.*\n"
    return ficha if ficha else "*No se encontró información.*"

# --- BUSQUEDA PROFUNDA DE DOMINIOS Y BASES DE DATOS ---
def deep_domain_scan(domain):
    resultado = f"🔍 *Deep Scan para:* `{domain}`\n"
    subdoms = buscar_subdominios(domain)
    if subdoms:
        resultado += f"\n🌐 *Subdominios vivos:* ({len(subdoms)})\n"
        for s in subdoms[:10]:
            resultado += f"- `{s}`\n"
    else:
        resultado += "\n🌐 *No se encontraron subdominios vivos.*\n"

    try:
        js_endpoints = buscar_js_endpoints(f"https://{domain}")
        if js_endpoints:
            resultado += f"\n🧩 *Endpoints JS encontrados:* ({len(js_endpoints)})\n"
            for e in js_endpoints[:10]:
                resultado += f"- `{e}`\n"
        else:
            resultado += "\n🧩 *No se encontraron endpoints JS.*\n"
    except Exception:
        resultado += "\n🧩 *Error al buscar endpoints JS.*\n"

    gh_leaks = buscar_github(domain)
    if gh_leaks:
        resultado += f"\n💻 *Resultados en GitHub:* ({len(gh_leaks)})\n"
        for g in gh_leaks[:10]:
            resultado += f"- {g}\n"
    else:
        resultado += "\n💻 *No se encontraron resultados en GitHub.*\n"

    resultado += "\n🛡️ *Escaneo de puertos (top 10):*\n"
    common_ports = [21, 22, 23, 25, 53, 80, 110, 143, 443, 3306]
    try:
        ip = socket.gethostbyname(domain)
        for port in common_ports:
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.settimeout(1)
            try:
                s.connect((ip, port))
                resultado += f"- `{port}`: ✅ *Abierto*\n"
            except Exception:
                resultado += f"- `{port}`: ❌ Cerrado\n"
            s.close()
    except Exception:
        resultado += "- ❌ No se pudo resolver el dominio para escaneo de puertos.\n"

    leaks = []
    if os.path.exists(LEAKS_FILE):
        with open(LEAKS_FILE, "r") as f:
            all_leaks = json.load(f)
            for leak in all_leaks:
                if domain in str(leak):
                    leaks.append(leak)
    if leaks:
        resultado += f"\n🗄️ *Leaks locales relacionados:* ({len(leaks)})\n"
        for l in leaks[:5]:
            resultado += f"- `{str(l)[:200]}`\n"
    else:
        resultado += "\n🗄️ *No se encontraron leaks locales relacionados.*\n"

    resultado += "\n🔎 *Escaneo completado.*"
    return resultado

# --- COMANDOS TELEGRAM CON TECLADO INLINE Y FORMATO EXCELENTE ---

@bot.message_handler(commands=['start'])
def cmd_start(message):
    user_id = message.from_user.id
    if es_baneado(user_id):
        bot.send_message(message.chat.id, "🚫 Has sido baneado del bot, grupo y canal.")
        return
    if not verificar_enlace(user_id):
        bot.send_message(
            message.chat.id,
            f"🚨 *Debes unirte al canal y grupo para usar el bot.*\n\n"
            f"👉 [Canal]({CANAL_LINK})\n"
            f"👉 [Grupo]({GRUPO_LINK})\n\n"
            "Una vez te unas, pulsa el botón para verificar.",
            reply_markup=mensaje_verificacion(),
            parse_mode="Markdown"
        )
        return
    config["usuarios"]["admin_chat_id"] = message.chat.id
    guardar_config(config)
    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.add(
        types.InlineKeyboardButton("DeepScan Dominio", callback_data="deepdomain"),
        types.InlineKeyboardButton("Buscar Leak", callback_data="leak"),
        types.InlineKeyboardButton("GitHub", callback_data="github"),
        types.InlineKeyboardButton("JS Endpoints", callback_data="js"),
        types.InlineKeyboardButton("Subdominios", callback_data="subdominios"),
        types.InlineKeyboardButton("DNI", callback_data="dni"),
        types.InlineKeyboardButton("Informe DNI", callback_data="informe"),
        types.InlineKeyboardButton("Teléfono", callback_data="telefono"),
        types.InlineKeyboardButton("Ficha", callback_data="ficha"),
    )

    # Enviar imagen de bienvenida si existe
    splash_path = "assets/splash.png"
    if os.path.exists(splash_path):
        with open(splash_path, 'rb') as photo:
            bot.send_photo(
                message.chat.id,
                photo,
                caption="👋 *Bienvenido a Patria Clone Bot (modo OSINT/Leaks/DeepScan).* \n\n"
                "Selecciona una opción o usa los comandos:\n"
                "• `/deepdomain <dominio>` - Búsqueda profunda de dominio\n"
                "• `/leak <texto>` - Analiza texto crudo, extrae USER:PASS, URLs, etc\n"
                "• `/github <query>` - Busca código en GitHub\n"
                "• `/js <url>` - Busca endpoints en JS de una web\n"
                "• `/subdominios <dominio>` - Busca subdominios vivos\n"
                "• `/dni <dni>` - Busca el DNI en leaks locales\n"
                "• `/informe <dni>` - Informe completo por DNI\n"
                "• `/telefono <número>` - Busca titulares por teléfono\n"
                "• `/ficha <dni|telefono>` - Ficha + mensajes\n"
                "\n*Solo para fines educativos y de auditoría.*\n"
                "\nTips:\n"
                "```\n"
                "• Usa /deepdomain para obtener TODO sobre un dominio.\n"
                "• Usa /leak para analizar dumps o leaks de texto.\n"
                "• Usa los botones para facilitar tu OSINT.\n"
                "```",
                reply_markup=markup
            )
    else:
        bot.send_message(
            message.chat.id,
            "👋 *Bienvenido a Patria Clone Bot (modo OSINT/Leaks/DeepScan).* \n\n"
            "Selecciona una opción o usa los comandos:\n"
            "• `/deepdomain <dominio>` - Búsqueda profunda de dominio\n"
            "• `/leak <texto>` - Analiza texto crudo, extrae USER:PASS, URLs, etc\n"
            "• `/github <query>` - Busca código en GitHub\n"
            "• `/js <url>` - Busca endpoints en JS de una web\n"
            "• `/subdominios <dominio>` - Busca subdominios vivos\n"
            "• `/dni <dni>` - Busca el DNI en leaks locales\n"
            "• `/informe <dni>` - Informe completo por DNI\n"
            "• `/telefono <número>` - Busca titulares por teléfono\n"
            "• `/ficha <dni|telefono>` - Ficha + mensajes\n"
            "\n*Solo para fines educativos y de auditoría.*\n"
            "\nTips:\n"
            "```\n"
            "• Usa /deepdomain para obtener TODO sobre un dominio.\n"
            "• Usa /leak para analizar dumps o leaks de texto.\n"
            "• Usa los botones para facilitar tu OSINT.\n"
            "```",
            reply_markup=markup
        )

@bot.callback_query_handler(func=lambda call: True)
def callback_query(call):
    user_id = call.from_user.id
    if es_baneado(user_id):
        bot.answer_callback_query(call.id, "🚫 Has sido baneado del bot, grupo y canal.", show_alert=True)
        return
    if call.data == "verificar_union":
        if verificar_enlace(user_id):
            bot.answer_callback_query(call.id, "✅ Verificación exitosa. Ya puedes usar el bot.", show_alert=True)
            cmd_start(call.message)
        else:
            bot.answer_callback_query(call.id, "❌ Aún no detectamos que te hayas unido. Únete al canal y grupo y vuelve a verificar.", show_alert=True)
    elif not verificar_enlace(user_id):
        bot.answer_callback_query(call.id, "❌ Debes unirte al canal y grupo para usar el bot.", show_alert=True)
        bot.send_message(
            call.message.chat.id,
            f"🚨 *Debes unirte al canal y grupo para usar el bot.*\n\n"
            f"👉 [Canal]({CANAL_LINK})\n"
            f"👉 [Grupo]({GRUPO_LINK})\n\n"
            "Una vez te unas, pulsa el botón para verificar.",
            reply_markup=mensaje_verificacion(),
            parse_mode="Markdown"
        )
        return
    elif call.data == "deepdomain":
        bot.send_message(call.message.chat.id, "🔎 Envía el dominio a analizar usando:\n`/deepdomain dominio.com`")
    elif call.data == "leak":
        bot.send_message(call.message.chat.id, "💧 Envía el texto crudo después de:\n`/leak <texto>`")
    elif call.data == "github":
        bot.send_message(call.message.chat.id, "💻 Envía la búsqueda después de:\n`/github <query>`")
    elif call.data == "js":
        bot.send_message(call.message.chat.id, "🧩 Envía la URL después de:\n`/js <url>`")
    elif call.data == "subdominios":
        bot.send_message(call.message.chat.id, "🌐 Envía el dominio después de:\n`/subdominios <dominio>`")
    elif call.data == "dni":
        bot.send_message(call.message.chat.id, "🆔 Envía el DNI después de:\n`/dni <dni>`")
    elif call.data == "informe":
        bot.send_message(call.message.chat.id, "📄 Envía el DNI después de:\n`/informe <dni>`")
    elif call.data == "telefono":
        bot.send_message(call.message.chat.id, "📞 Envía el número después de:\n`/telefono <número>`")
    elif call.data == "ficha":
        bot.send_message(call.message.chat.id, "🕵️ Envía el DNI o teléfono después de:\n`/ficha <dni|telefono>`")

# --- COMANDOS SOLO SI EL USUARIO ESTÁ VERIFICADO ---
@bot.message_handler(commands=['deepdomain'])
@acceso_requerido
def cmd_deepdomain(message):
    dominio = message.text.partition(' ')[2].strip()
    if not dominio:
        bot.send_message(message.chat.id, "Envía el dominio después de `/deepdomain dominio.com`")
        return

    bot.send_chat_action(message.chat.id, "typing")
    bot.send_message(message.chat.id, f"🔍 *Iniciando escaneo profundo de:* `{dominio}`\n\n⏳ Esto puede tomar unos segundos...")

    resultado = deep_domain_scan(dominio)

    # Dividir el mensaje si es demasiado largo
    if len(resultado) > 4000:
        partes = [resultado[i:i+4000] for i in range(0, len(resultado), 4000)]
        for parte in partes:
            bot.send_message(message.chat.id, parte, parse_mode="Markdown")
    else:
        bot.send_message(message.chat.id, resultado, parse_mode="Markdown")

@bot.message_handler(commands=['leak'])
@acceso_requerido
def cmd_leak(message):
    texto = message.text.partition(' ')[2].strip()
    if not texto:
        bot.send_message(message.chat.id, "Envía el texto crudo después de `/leak <texto>`")
        return

    bot.send_chat_action(message.chat.id, "typing")

    resumen = "🔍 *Analizando texto...*\n\n"
    userpass = extraer_userpass(texto)
    if userpass:
        resumen += f"👤 *USER:PASS encontrados* ({len(userpass)}):\n"
        for u, p in userpass[:10]:
            resumen += f"- `{u}:{p}`\n"
        if len(userpass) > 10:
            resumen += f"- ... y {len(userpass) - 10} más\n"
    else:
        resumen += "👤 *No se encontraron USER:PASS*\n"

    urls = extraer_urls(texto)
    if urls:
        resumen += f"\n🔗 *URLs únicas* ({len(urls)}):\n"
        for u in urls[:10]:
            resumen += f"- `{u}`\n"
        if len(urls) > 10:
            resumen += f"- ... y {len(urls) - 10} más\n"
    else:
        resumen += "\n🔗 *No se encontraron URLs*\n"

    lineas_unicas = quitar_lineas_repetidas(texto)
    resumen += "\n📝 *Líneas únicas:*\n"
    resumen += "```\n" + lineas_unicas[:500] + "\n```"

    if len(lineas_unicas) > 500:
        resumen += f"\n*Nota:* Mostrando solo las primeras 500 líneas de {len(lineas_unicas)}"

    guardar_leak({"texto": texto, "userpass": userpass, "urls": urls, "timestamp": time.strftime("%Y-%m-%d %H:%M:%S")})

    # Dividir el mensaje si es demasiado largo
    if len(resumen) > 4000:
        partes = [resumen[i:i+4000] for i in range(0, len(resumen), 4000)]
        for parte in partes:
            bot.send_message(message.chat.id, parte, parse_mode="Markdown")
    else:
        bot.send_message(message.chat.id, resumen, parse_mode="Markdown")

@bot.message_handler(commands=['github'])
@acceso_requerido
def cmd_github(message):
    query = message.text.partition(' ')[2].strip()
    if not query:
        bot.send_message(message.chat.id, "Envía la búsqueda después de `/github <query>`")
        return

    bot.send_chat_action(message.chat.id, "typing")
    bot.send_message(message.chat.id, f"🔍 *Buscando en GitHub:* `{query}`")

    resultados = buscar_github(query)
    if resultados:
        msg = f"💻 *Resultados GitHub para* `{query}`:\n\n"
        for r in resultados:
            msg += f"- {r}\n"
        bot.send_message(message.chat.id, msg)
    else:
        bot.send_message(message.chat.id, f"❌ *No se encontraron resultados en GitHub para* `{query}`")

@bot.message_handler(commands=['js'])
@acceso_requerido
def cmd_js(message):
    url = message.text.partition(' ')[2].strip()
    if not url:
        bot.send_message(message.chat.id, "Envía la URL después de `/js <url>`")
        return

    bot.send_chat_action(message.chat.id, "typing")
    bot.send_message(message.chat.id, f"🔍 *Buscando endpoints JS en:* `{url}`")

    endpoints = buscar_js_endpoints(url)
    if endpoints:
        msg = f"🧩 *Endpoints JS encontrados en* `{url}`:\n\n"
        for e in endpoints[:10]:
            msg += f"- `{e}`\n"
        if len(endpoints) > 10:
            msg += f"- ... y {len(endpoints) - 10} más\n"
        bot.send_message(message.chat.id, msg)
    else:
        bot.send_message(message.chat.id, f"❌ *No se encontraron endpoints JS en* `{url}`")

@bot.message_handler(commands=['subdominios'])
@acceso_requerido
def cmd_subdominios(message):
    dominio = message.text.partition(' ')[2].strip()
    if not dominio:
        bot.send_message(message.chat.id, "Envía el dominio después de `/subdominios <dominio>`")
        return

    bot.send_chat_action(message.chat.id, "typing")
    bot.send_message(message.chat.id, f"🔍 *Buscando subdominios para:* `{dominio}`")

    vivos = buscar_subdominios(dominio)
    if vivos:
        msg = f"🌐 *Subdominios vivos para* `{dominio}`:\n\n"
        for v in vivos[:10]:
            msg += f"- `{v}`\n"
        if len(vivos) > 10:
            msg += f"- ... y {len(vivos) - 10} más\n"
        bot.send_message(message.chat.id, msg)
    else:
        bot.send_message(message.chat.id, f"❌ *No se encontraron subdominios vivos para* `{dominio}`")

@bot.message_handler(commands=['dni'])
@acceso_requerido
def cmd_dni(message):
    dni = message.text.partition(' ')[2].strip()
    if not dni:
        bot.send_message(message.chat.id, "Envía el DNI después de `/dni <dni>`")
        return

    bot.send_chat_action(message.chat.id, "typing")
    bot.send_message(message.chat.id, f"🔍 *Buscando DNI:* `{dni}`")

    resultados = buscar_dni_databreach(dni)
    if resultados:
        msg = f"🆔 *DNI encontrado en {len(resultados)} leaks:*\n\n"
        for r in resultados[:5]:
            msg += f"- `{str(r)[:200]}`\n"
        if len(resultados) > 5:
            msg += f"- ... y {len(resultados) - 5} más\n"
        bot.send_message(message.chat.id, msg)
    else:
        bot.send_message(message.chat.id, f"❌ *No se encontró el DNI* `{dni}` *en leaks locales*")

@bot.message_handler(commands=['informe'])
@acceso_requerido
def cmd_informe(message):
    dni = message.text.partition(' ')[2].strip()
    if not dni:
        bot.send_message(message.chat.id, "Envía el DNI después de `/informe <dni>`")
        return

    bot.send_chat_action(message.chat.id, "typing")
    bot.send_message(message.chat.id, f"📄 *Generando informe para DNI:* `{dni}`")

    informe = informe_completo_dni(dni)

    if len(informe) > 4000:
        partes = [informe[i:i+4000] for i in range(0, len(informe), 4000)]
        for parte in partes:
            bot.send_message(message.chat.id, parte, parse_mode="Markdown")
    else:
        bot.send_message(message.chat.id, informe, parse_mode="Markdown")

@bot.message_handler(commands=['telefono'])
@acceso_requerido
def cmd_telefono(message):
    telefono = message.text.partition(' ')[2].strip()
    if not telefono:
        bot.send_message(message.chat.id, "Envía el número después de `/telefono <número>`")
        return

    bot.send_chat_action(message.chat.id, "typing")
    bot.send_message(message.chat.id, f"🔍 *Buscando teléfono:* `{telefono}`")

    resultados = buscar_titular_telefono(telefono)
    if resultados:
        msg = f"📞 *Teléfono encontrado en {len(resultados)} leaks:*\n\n"
        for r in resultados[:5]:
            msg += f"- `{str(r)[:200]}`\n"
        if len(resultados) > 5:
            msg += f"- ... y {len(resultados) - 5} más\n"
        bot.send_message(message.chat.id, msg)
    else:
        bot.send_message(message.chat.id, f"❌ *No se encontró el teléfono* `{telefono}` *en leaks locales*")

@bot.message_handler(commands=['ficha'])
@acceso_requerido
def cmd_ficha(message):
    arg = message.text.partition(' ')[2].strip()
    if not arg:
        bot.send_message(message.chat.id, "Envía el DNI o teléfono después de `/ficha <dni|telefono>`")
        return

    bot.send_chat_action(message.chat.id, "typing")

    if arg.isdigit() and len(arg) >= 6:
        bot.send_message(message.chat.id, f"🕵️ *Generando ficha para DNI:* `{arg}`")
        ficha = ficha_estafador(dni=arg)
    else:
        bot.send_message(message.chat.id, f"🕵️ *Generando ficha para teléfono:* `{arg}`")
        ficha = ficha_estafador(telefono=arg)

    if len(ficha) > 4000:
        partes = [ficha[i:i+4000] for i in range(0, len(ficha), 4000)]
        for parte in partes:
            bot.send_message(message.chat.id, parte, parse_mode="Markdown")
    else:
        bot.send_message(message.chat.id, ficha, parse_mode="Markdown")

# --- CONTROL DE MENSAJES EN GRUPO: ACTIVACIÓN Y BANEO POR "CALLAR" ---
CALLAR_PALABRAS = ["callate", "shh", "shhh", "shhhh", "sh", "cállate", "silencio", "cállese", "mute", "cállate bot", "calla bot"]

@bot.message_handler(func=lambda m: m.chat.type in ["group", "supergroup"])
def handler_grupo(m):
    user_id = m.from_user.id
    if es_baneado(user_id):
        try:
            bot.kick_chat_member(m.chat.id, user_id)
        except Exception:
            pass
        return

    texto = m.text or ""

    # Si contiene palabras de callar, banear
    for palabra in CALLAR_PALABRAS:
        if palabra in texto.lower():
            try:
                bot.send_message(m.chat.id, f"🚫 @{m.from_user.username} ha sido baneado por intentar callar al bot.",
                                reply_to_message_id=m.message_id)
                bot.kick_chat_member(m.chat.id, user_id)
            except Exception:
                pass
            banear_usuario(user_id)
            try:
                bot.send_message(user_id, "🚫 Has sido baneado del bot, grupo y canal por intentar callar al bot.")
            except Exception:
                pass
            return

    # Si el mensaje es un comando, procesarlo directamente
    if texto.startswith("/"):
        # Crear un mensaje falso para procesar
        fake_msg = types.Message(
            message_id=m.message_id,
            from_user=m.from_user,
            date=m.date,
            chat=m.chat,
            content_type="text",
            options={},
            json_string=""
        )
        fake_msg.text = texto

        # Buscar handler adecuado
        for handler in bot.message_handlers:
            if hasattr(handler, "filters") and handler.filters:
                if handler.filters(fake_msg):
                    try:
                        handler.function(fake_msg)
                    except Exception as e:
                        bot.send_message(m.chat.id, f"❌ Error al procesar el comando: {str(e)}",
                                        reply_to_message_id=m.message_id)
                    break

def saludo_inicio():
    # Enviar mensaje a todos los usuarios registrados
    for user_id in config["usuarios"]:
        if user_id != "admin_chat_id":
            try:
                bot.send_message(user_id, "🤖 *El bot Patria Clone (OSINT/Leaks/DeepScan) ha sido iniciado y está en línea.*")
            except Exception:
                pass

    # Enviar mensaje al canal y grupo
    try:
        bot.send_message(CANAL_ID, "🤖 *El bot Patria Clone (OSINT/Leaks/DeepScan) ha sido iniciado y está en línea.*")
    except Exception:
        pass

    try:
        bot.send_message(GRUPO_ID, "🤖 *El bot Patria Clone (OSINT/Leaks/DeepScan) ha sido iniciado y está en línea.*")
    except Exception:
        pass

def despedida(signal_received=None, frame=None):
    # Enviar mensaje a todos los usuarios registrados
    for user_id in config["usuarios"]:
        if user_id != "admin_chat_id":
            try:
                bot.send_message(user_id, "🤖 *El bot Patria Clone (OSINT/Leaks/DeepScan) se está apagando...*")
            except Exception:
                pass

    # Enviar mensaje al canal y grupo
    try:
        bot.send_message(CANAL_ID, "🤖 *El bot Patria Clone (OSINT/Leaks/DeepScan) se está apagando...*")
    except Exception:
        pass

    try:
        bot.send_message(GRUPO_ID, "🤖 *El bot Patria Clone (OSINT/Leaks/DeepScan) se está apagando...*")
    except Exception:
        pass

    sys.exit(0)

# --- EJECUCIÓN PRINCIPAL ---
if __name__ == "__main__":
    # Configurar manejo de señales para apagado elegante
    signal.signal(signal.SIGINT, despedida)
    signal.signal(signal.SIGTERM, despedida)

    # Enviar saludo de inicio
    saludo_inicio()

    print("🤖 Bot Patria Clone (OSINT/Leaks/DeepScan) iniciado...")
    bot.infinity_polling()
