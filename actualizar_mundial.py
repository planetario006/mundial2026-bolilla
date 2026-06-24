# -*- coding: utf-8 -*-
"""
actualizar_mundial.py — Mundial 2026 · Bolilla (versión nube)
================================================================
Misma fuente y misma lógica de scraping que el script original
(actualizar_mundial_wikipedia.py): Wikipedia en español, vía su API
oficial. La diferencia es la salida: en vez de escribir en un .xlsm a
través de macros VBA (lo que obligaba a tener Windows + Excel instalado
localmente), este script guarda los partidos en matches.json y delega
en mundial_core.py el cálculo de clasificaciones/puntos/bombos.

Pensado para ejecutarse SIN supervisión (cron / GitHub Actions): no hay
ningún input() ni MsgBox que pueda dejarlo colgado esperando a que
alguien pulse algo.

Reglas de fusión con lo ya guardado en matches.json:
  - Gol/tarjetas/fase/grupo/fecha: se actualizan siempre con el último
    dato de Wikipedia (puede corregir errores de tipeo de la fuente).
  - penfall_local/visit y penpar_local/visit (penaltis fallados/parados):
    NUNCA se tocan automáticamente. Si no existían, se crean a 0; si ya
    tienen un valor (puesto a mano), se respeta siempre.

Uso:
    python actualizar_mundial.py                  # actualiza todo
    python actualizar_mundial.py --fase grupos
    python actualizar_mundial.py --fase eliminacion
    python actualizar_mundial.py --grupo A
    python actualizar_mundial.py --fase octavos
"""

import re
import sys
import time
import random
import argparse
import logging
from pathlib import Path

import requests

import mundial_core as core

BASE_DIR = Path(__file__).parent
MATCHES_PATH = BASE_DIR / "matches.json"
MANUAL_PATH = BASE_DIR / "manual_overrides.json"
SALIDA_PATH = BASE_DIR / "docs" / "data.json"
LOG_PATH = BASE_DIR / "log_mundial.txt"

API_ES = "https://es.wikipedia.org/w/api.php"

# ─────────────────────────────────────────────────────────────────────────────
# ¡IMPORTANTE! — Política de User-Agent de Wikimedia
# ─────────────────────────────────────────────────────────────────────────────
# Wikimedia exige (no es opcional) un User-Agent identificable con datos de
# contacto reales: https://foundation.wikimedia.org/wiki/Policy:Wikimedia_Foundation_User-Agent_Policy
# Si el contacto no es reconocible, te clasifican directamente en el nivel más
# bajo de su límite global de peticiones (500/hora sin autenticar, a fecha de
# 2026) en vez del nivel normal para herramientas identificadas correctamente.
#
# CAMBIA la siguiente URL por la de tu propio repositorio en cuanto lo crees
# en GitHub (o pon tu email). Es la única línea que tienes que tocar.
CONTACTO = "https://github.com/planetario006/mundial2026-bolilla"  # <-- CAMBIA ESTO

HEADERS = {
    "User-Agent": f"Mundial2026Bolilla/1.0 ({CONTACTO}) python-requests/{requests.__version__}"
}

# Sesión HTTP reutilizable: evita reabrir conexión en cada una de las 17
# páginas y mantiene las mismas cabeceras en todas las peticiones.
SESSION = requests.Session()
SESSION.headers.update(HEADERS)

# Ritmo de peticiones: 1 sola a la vez (nunca en paralelo), con una pausa
# entre página y página. Con esto, una ejecución completa (12 grupos + 5
# fases eliminatorias = 17 páginas) hace ~34 peticiones/hora si el workflow
# corre cada 30 min — muy por debajo de cualquier límite de Wikimedia, tanto
# si se cuenta por hora como si se cuenta por segundo (recomiendan <5 req/s
# y ≤3 en paralelo; aquí vamos secuencial y a ~1 req/s).
PAUSA_ENTRE_PAGINAS = 1.0
REINTENTOS_MAXIMOS = 4

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    handlers=[
        logging.FileHandler(LOG_PATH, encoding="utf-8"),
        logging.StreamHandler(sys.stdout),
    ],
)
log = logging.getLogger(__name__)

if "TU-USUARIO" in CONTACTO:
    log.warning(
        "CONTACTO sin personalizar todavia (sigue siendo el placeholder). "
        "Cambia la constante CONTACTO en actualizar_mundial.py por la URL de tu "
        "repo real antes de dejarlo corriendo en serio: sin un contacto valido, "
        "Wikimedia puede tratar este trafico como no identificado y aplicar el "
        "limite de peticiones mas bajo."
    )

# ─────────────────────────────────────────────────────────────────────────────
# MAPAS DE NOMBRES Y FASES  (idénticos al script original)
# ─────────────────────────────────────────────────────────────────────────────

NOMBRE_MAP = {
    "México": "México", "Sudáfrica": "Sudáfrica", "Corea del Sur": "Corea del Sur",
    "República Checa": "Chequia", "Chequia": "Chequia", "Canadá": "Canadá",
    "Bosnia y Herzegovina": "Bosnia", "Bosnia-Herzegovina": "Bosnia",
    "Países Bajos": "Países Bajos", "Estados Unidos": "EE.UU.", "España": "España",
    "Alemania": "Alemania", "Brasil": "Brasil", "Francia": "Francia",
    "Inglaterra": "Inglaterra", "Argentina": "Argentina", "Portugal": "Portugal",
    "Marruecos": "Marruecos", "Croacia": "Croacia", "Bélgica": "Bélgica",
    "Colombia": "Colombia", "Suecia": "Suecia", "Noruega": "Noruega",
    "Uruguay": "Uruguay", "Senegal": "Senegal", "Túnez": "Túnez", "Ecuador": "Ecuador",
    "Suiza": "Suiza", "Arabia Saudí": "Arabia Saudí", "Arabia Saudita": "Arabia Saudí",
    "Turquía": "Turquía", "Escocia": "Escocia", "Paraguay": "Paraguay",
    "Austria": "Austria", "Australia": "Australia", "Costa de Marfil": "Costa de Marfil",
    "Egipto": "Egipto", "Nueva Zelanda": "Nueva Zelanda", "Argelia": "Argelia",
    "Rep. Dem. del Congo": "R. D. Congo", "República Democrática del Congo": "R. D. Congo",
    "Catar": "Catar", "Irak": "Irak", "Panamá": "Panamá", "Uzbekistán": "Uzbekistán",
    "Haití": "Haití", "Irán": "Irán", "Jordania": "Jordania", "Ghana": "Ghana",
    "Curazao": "Curazao", "Cabo Verde": "Cabo Verde", "Japón": "Japón",
    "MEX": "México", "RSA": "Sudáfrica", "KOR": "Corea del Sur", "CZE": "Chequia",
    "CAN": "Canadá", "BIH": "Bosnia", "NED": "Países Bajos", "ESP": "España",
    "GER": "Alemania", "BRA": "Brasil", "FRA": "Francia", "ENG": "Inglaterra",
    "ARG": "Argentina", "POR": "Portugal", "MAR": "Marruecos", "CRO": "Croacia",
    "BEL": "Bélgica", "COL": "Colombia", "SWE": "Suecia", "NOR": "Noruega",
    "URU": "Uruguay", "SEN": "Senegal", "TUN": "Túnez", "ECU": "Ecuador",
    "SUI": "Suiza", "KSA": "Arabia Saudí", "TUR": "Turquía", "SCO": "Escocia",
    "PAR": "Paraguay", "AUT": "Austria", "AUS": "Australia", "CIV": "Costa de Marfil",
    "EGY": "Egipto", "NZL": "Nueva Zelanda", "ALG": "Argelia", "COD": "R. D. Congo",
    "QAT": "Catar", "IRQ": "Irak", "PAN": "Panamá", "UZB": "Uzbekistán",
    "HAI": "Haití", "IRN": "Irán", "JOR": "Jordania", "GHA": "Ghana",
    "CUW": "Curazao", "CPV": "Cabo Verde", "JPN": "Japón",
    "Mexico": "México", "South Africa": "Sudáfrica", "South Korea": "Corea del Sur",
    "Czech Republic": "Chequia", "Canada": "Canadá", "Netherlands": "Países Bajos",
    "United States": "EE.UU.", "USA": "EE.UU.", "Spain": "España", "Germany": "Alemania",
    "Brazil": "Brasil", "France": "Francia", "England": "Inglaterra",
    "Morocco": "Marruecos", "Croatia": "Croacia", "Belgium": "Bélgica",
    "Sweden": "Suecia", "Norway": "Noruega", "Tunisia": "Túnez",
    "Switzerland": "Suiza", "Saudi Arabia": "Arabia Saudí", "Turkey": "Turquía",
    "Scotland": "Escocia", "Ivory Coast": "Costa de Marfil", "Egypt": "Egipto",
    "New Zealand": "Nueva Zelanda", "Algeria": "Argelia", "Qatar": "Catar",
    "Iraq": "Irak", "Panama": "Panamá", "Uzbekistan": "Uzbekistán", "Haiti": "Haití",
    "Iran": "Irán", "Jordan": "Jordania", "Japan": "Japón", "Cape Verde": "Cabo Verde",
    "DR Congo": "R. D. Congo",
}

# Grupos del Mundial 2026: A-L, 12 grupos.
# (El script original solo cubría A-K — 11 — y se dejaba el Grupo L sin
# actualizar nunca; se corrige aquí.)
GRUPOS = list("ABCDEFGHIJKL")

FASES_ELIMINACION = [
    {"pagina": "Anexo:Dieciseisavos de final de la Copa Mundial de Fútbol de 2026",
     "fase_txt": "Dieciseisavos de final",},
    {"pagina": "Anexo:Octavos de final de la Copa Mundial de Fútbol de 2026",
     "fase_txt": "Octavos de final",},
    {"pagina": "Anexo:Cuartos de final de la Copa Mundial de Fútbol de 2026",
     "fase_txt": "Cuartos de final",},
    {"pagina": "Anexo:Semifinales de la Copa Mundial de Fútbol de 2026",
     "fase_txt": "Semifinales",},
    {"pagina": "Anexo:Final de la Copa Mundial de Fútbol de 2026",
     "fase_txt": "Final",},
]

_PREREQ = {
    "Dieciseisavos de final": None,
    "Octavos de final":       "Dieciseisavos de final",
    "Cuartos de final":       "Octavos de final",
    "Semifinales":            "Cuartos de final",
    "Final":                  "Semifinales",
}

# ─────────────────────────────────────────────────────────────────────────────
# UTILIDADES DE SCRAPING (idénticas al script original)
# ─────────────────────────────────────────────────────────────────────────────

def traducir(nombre: str) -> str:
    n = nombre.strip()
    return NOMBRE_MAP.get(n, n)


def obtener_wikitext(pagina: str) -> str:
    """Descarga el wikitext de una página, con reintentos corteses si la API
    responde 429 (demasiadas peticiones) o 503 (servidor saturado / maxlag).

    Sigue las prácticas que pide Wikimedia para herramientas automatizadas:
    respeta la cabecera Retry-After si la manda el servidor, y si no, aplica
    un backoff exponencial con jitter antes de reintentar. Tras agotar los
    reintentos, propaga la excepción (quien la llama ya la captura y se
    limita a anotar esa página como "no disponible esta vez", sin tirar
    abajo el resto de la actualización).
    """
    params = {
        "action": "parse",
        "page": pagina,
        "prop": "wikitext",
        "format": "json",
        "formatversion": "2",
        "maxlag": 5,  # buena práctica: si los servidores van con retraso, que nos lo digan en vez de forzar
    }

    ultimo_error = None
    for intento in range(1, REINTENTOS_MAXIMOS + 1):
        try:
            r = SESSION.get(API_ES, params=params, timeout=20)

            if r.status_code in (429, 503):
                espera = r.headers.get("Retry-After")
                espera = float(espera) if espera else (2 ** intento) + random.uniform(0, 1)
                log.warning(f"     HTTP {r.status_code} en «{pagina}» — esperando {espera:.1f}s (intento {intento}/{REINTENTOS_MAXIMOS})")
                time.sleep(espera)
                continue

            r.raise_for_status()
            data = r.json()
            if "error" in data:
                # maxlag y errores similares también vienen como {"error": {...}} con 200 OK
                if data["error"].get("code") == "maxlag":
                    espera = (2 ** intento) + random.uniform(0, 1)
                    log.warning(f"     maxlag en «{pagina}» — esperando {espera:.1f}s (intento {intento}/{REINTENTOS_MAXIMOS})")
                    time.sleep(espera)
                    continue
                raise RuntimeError(data["error"].get("info", "error desconocido"))

            return data["parse"]["wikitext"]

        except (requests.exceptions.ConnectionError, requests.exceptions.Timeout) as e:
            ultimo_error = e
            espera = (2 ** intento) + random.uniform(0, 1)
            log.warning(f"     Fallo de red en «{pagina}» ({e.__class__.__name__}) — esperando {espera:.1f}s (intento {intento}/{REINTENTOS_MAXIMOS})")
            time.sleep(espera)

    raise RuntimeError(f"Agotados los {REINTENTOS_MAXIMOS} reintentos para «{pagina}»" + (f": {ultimo_error}" if ultimo_error else ""))


def extraer_bloques_partido(wikitext: str) -> list:
    patron = re.compile(
        r"\{\{\s*(?:[Pp]artido de f[úu]tbol|[Ff]utbolbox|[Ff]ootball box|[Ff]ootball [Bb]ox|[Ff]b[Bb]ox|[Pp]artido)\b",
        re.IGNORECASE,
    )
    posiciones = [m.start() for m in patron.finditer(wikitext)]
    if not posiciones:
        return []
    bloques = []
    for i, inicio in enumerate(posiciones):
        fin = posiciones[i + 1] if i + 1 < len(posiciones) else len(wikitext)
        bloques.append(wikitext[inicio:fin])
    return bloques


def _campo(bloque: str, nombre: str) -> str:
    patron_campo = re.compile(r"\|\s*" + re.escape(nombre) + r"\s*=\s*", re.IGNORECASE)
    m = patron_campo.search(bloque)
    if not m:
        return ""
    inicio_valor = m.end()
    depth = 0
    i = inicio_valor
    n = len(bloque)
    chars = []
    while i < n:
        two = bloque[i:i + 2]
        if two == "{{":
            depth += 1
            chars.append("{{")
            i += 2
        elif two == "}}":
            if depth == 0:
                break
            depth -= 1
            chars.append("}}")
            i += 2
        elif bloque[i] == "|" and depth == 0:
            break
        elif bloque[i] == "\n" and depth == 0:
            resto = bloque[i + 1:].lstrip(" \t")
            if resto.startswith("|") or resto.startswith("}}"):
                break
            chars.append(bloque[i])
            i += 1
        else:
            chars.append(bloque[i])
            i += 1
    return "".join(chars).strip()


def _limpiar_plantillas(texto: str) -> str:
    texto = re.sub(r"\[\[(?:[^\]|]*\|)?([^\]]*)\]\]", r"\1", texto)
    texto = re.sub(r"<ref[^>]*>.*?</ref>", "", texto, flags=re.DOTALL)
    texto = re.sub(r"<[^>]+>", "", texto)
    texto = re.sub(r"\{\{bandera2?\|([^}|]+).*?\}\}", r"\1", texto)
    texto = re.sub(r"\{\{[^{}]*\}\}", "", texto)
    texto = re.sub(r"\s+", " ", texto)
    return texto.strip()


def contar_tarjetas(texto_booking: str) -> dict:
    if not texto_booking:
        return {"ta": 0, "doble_a": 0, "rd": 0}
    t = texto_booking.lower()
    doble_a_en = len(re.findall(r"yel\|[^a-zA-Z]*sent\s*off", t))
    total_yel = len(re.findall(r"yel\b", t))
    total_sentoff = len(re.findall(r"sent\s*off", t))
    ta_en = max(0, total_yel - doble_a_en)
    rd_en = max(0, total_sentoff - doble_a_en)
    doble_a_es = len(re.findall(r"\{\{\s*(?:2amarilla|doble\s*amarilla|segunda\s*amarilla|second\s*yellow)\b", t))
    doble_a_es += len(re.findall(r"\{\{\s*expulsado\s*\|\s*1\s*\}\}", t))
    amarillas_es = len(re.findall(r"\{\{\s*(?:ama|amarilla|yellow)\b", t))
    expulsiones_es = len(re.findall(r"\{\{\s*(?:roja|red)\b", t))
    expulsiones_es += len(re.findall(r"\{\{\s*expulsado\s*(?:\|\s*[02]\s*)?\}\}", t))
    return {
        "ta": ta_en + amarillas_es,
        "doble_a": doble_a_en + doble_a_es,
        "rd": rd_en + expulsiones_es,
    }


def extraer_tarjetas_desde_bloque(bloque: str):
    booking1 = _campo(bloque, "booking1") or _campo(bloque, "bookings1") or ""
    booking2 = _campo(bloque, "booking2") or _campo(bloque, "bookings2") or ""
    if booking1 or booking2:
        return contar_tarjetas(booking1), contar_tarjetas(booking2)

    tablas = re.findall(r"\{\|\s*style=\"font-size:90%.*?\|\}", bloque, re.DOTALL)
    if len(tablas) >= 2:
        return contar_tarjetas(tablas[0]), contar_tarjetas(tablas[1])

    tarjetas_local = {"ta": 0, "doble_a": 0, "rd": 0}
    tarjetas_visit = {"ta": 0, "doble_a": 0, "rd": 0}
    mAma = re.search(r"!colspan=3\|\s*Amonestaciones(.*?)!(?:colspan=3\|\s*Expulsiones|Árbitro|\|\})", bloque, re.S | re.IGNORECASE)
    if mAma:
        partes = re.split(r"\|width=50%\s*colspan=2\|", mAma.group(1), maxsplit=1)
        if len(partes) == 2:
            tl, tv = contar_tarjetas(partes[0]), contar_tarjetas(partes[1])
            tarjetas_local["ta"] += tl["ta"]
            tarjetas_visit["ta"] += tv["ta"]
    mExp = re.search(r"!colspan=3\|\s*Expulsiones(.*?)!(?:Árbitro|\|\})", bloque, re.S | re.IGNORECASE)
    if mExp:
        partes = re.split(r"\|width=50%\s*colspan=2\|", mExp.group(1), maxsplit=1)
        if len(partes) == 2:
            tl, tv = contar_tarjetas(partes[0]), contar_tarjetas(partes[1])
            tarjetas_local["rd"] += tl["rd"]; tarjetas_local["doble_a"] += tl["doble_a"]
            tarjetas_visit["rd"] += tv["rd"]; tarjetas_visit["doble_a"] += tv["doble_a"]
    return tarjetas_local, tarjetas_visit


def parsear_bloque(bloque: str, fase_txt: str, grupo_letra: str) -> dict | None:
    t1_raw = _campo(bloque, "equipo1") or _campo(bloque, "team1") or _campo(bloque, "local") or ""
    t2_raw = _campo(bloque, "equipo2") or _campo(bloque, "team2") or _campo(bloque, "visitante") or _campo(bloque, "visita") or ""
    t1_raw = _limpiar_plantillas(t1_raw)
    t2_raw = _limpiar_plantillas(t2_raw)
    t1_raw = re.sub(r"\{\{[^}]*\}\}", "", t1_raw).strip()
    t2_raw = re.sub(r"\{\{[^}]*\}\}", "", t2_raw).strip()
    if not t1_raw or not t2_raw:
        return None
    t1, t2 = traducir(t1_raw), traducir(t2_raw)
    res_raw = _campo(bloque, "resultado") or _campo(bloque, "marcador") or _campo(bloque, "score") or ""
    res_limpio = re.sub(r"\{\{[^}]+\}\}", "", res_raw).strip()
    res_limpio = re.sub(r"\([^)]*\)", "", res_limpio)
    res_limpio = re.sub(r"\{\{[^}]+\}\}", "", res_limpio)
    m_res = re.search(r"^\s*(\d+)\s*[-–:]\s*(\d+)", res_limpio)
    gf1 = gf2 = None
    if m_res:
        gf1, gf2 = int(m_res.group(1)), int(m_res.group(2))
    else:
        g1_raw = _campo(bloque, "goles1") or _campo(bloque, "goals1") or ""
        g2_raw = _campo(bloque, "goles2") or _campo(bloque, "goals2") or ""
        try:
            gf1 = int(re.search(r"\d+", g1_raw).group()) if re.search(r"\d+", g1_raw) else None
            gf2 = int(re.search(r"\d+", g2_raw).group()) if re.search(r"\d+", g2_raw) else None
        except (AttributeError, ValueError):
            pass
    fecha_raw = _campo(bloque, "fecha") or _campo(bloque, "date") or ""
    m_tpl_fecha = re.search(r"\{\{\s*fecha\s*\|\s*(\d{1,2})\s*\|\s*(\d{1,2})\s*\|\s*(\d{4})", fecha_raw, re.IGNORECASE)
    if m_tpl_fecha:
        dia, mes, anio = int(m_tpl_fecha.group(1)), int(m_tpl_fecha.group(2)), int(m_tpl_fecha.group(3))
        fecha = f"{anio}-{mes:02d}-{dia:02d}"
    else:
        MESES = {"enero": 1, "febrero": 2, "marzo": 3, "abril": 4, "mayo": 5, "junio": 6,
                  "julio": 7, "agosto": 8, "septiembre": 9, "octubre": 10, "noviembre": 11, "diciembre": 12}
        m_fecha2 = re.search(r"(\d{1,2})\s+de\s+(\w+)\s+de\s+(\d{4})", fecha_raw, re.IGNORECASE)
        if m_fecha2:
            dia = int(m_fecha2.group(1))
            mes = MESES.get(m_fecha2.group(2).lower(), 0)
            anio = int(m_fecha2.group(3))
            fecha = f"{anio}-{str(mes).zfill(2)}-{str(dia).zfill(2)}" if mes else ""
        else:
            fecha = ""
    cards1, cards2 = extraer_tarjetas_desde_bloque(bloque)
 
    # ── NUEVO: número de partido (M73, M74…) ──────────────────────
    # Wikipedia almacena el número del partido en el campo "partido"
    # de la plantilla. Se prueban nombres alternativos por robustez.
    num_raw = (
        _campo(bloque, "partido")
        or _campo(bloque, "número")
        or _campo(bloque, "numero")
        or _campo(bloque, "match")
        or _campo(bloque, "id")
        or ""
    )
    num_str = re.sub(r"\D", "", num_raw.strip())
    match_num = int(num_str) if num_str else None
    # ──────────────────────────────────────────────────────────────
 
    return {
        "team1": t1, "team2": t2, "fecha": fecha, "gf1": gf1, "gf2": gf2,
        "cards1": cards1, "cards2": cards2, "fase": fase_txt, "grupo": grupo_letra,
        "match_num": match_num,   # ← NUEVO
    }


def partidos_de_pagina(pagina: str, fase_txt: str, grupo_letra: str = "") -> list:
    log.info(f"  -> Página: «{pagina}»")
    try:
        wikitext = obtener_wikitext(pagina)
    except Exception as e:
        log.warning(f"     No disponible todavía (o error de red): {e}")
        return []
    bloques = extraer_bloques_partido(wikitext)
    log.info(f"     {len(bloques)} bloque(s) de partido detectados")
    resultados = [parsear_bloque(b, fase_txt, grupo_letra) for b in bloques]
    resultados = [p for p in resultados if p]
    log.info(f"     {len(resultados)} partido(s) con resultado")
    return resultados


def procesar_grupos(filtro_grupo=None) -> list:
    grupos = [filtro_grupo] if filtro_grupo else GRUPOS
    todos = []
    for g in grupos:
        pagina = f"Anexo:Grupo {g} de la Copa Mundial de Fútbol de 2026"
        todos.extend(partidos_de_pagina(pagina, core.FASE_GRUPOS_TXT, g))
        time.sleep(PAUSA_ENTRE_PAGINAS)
    return todos


def procesar_eliminacion(filtro_fase=None, matches_actuales=None) -> list:
    """Descarga partidos de las fases eliminatorias de Wikipedia.
 
    Sin filtro_fase aplica lógica eficiente:
    - Dieciseisavos: siempre (equipos se clasifican durante grupos).
    - Resto: solo si su fase prerequisito tiene al menos un partido
      con resultado en matches_actuales.
 
    Caso especial Semifinales: la página contiene los 2 partidos de
    semis y el partido por el tercer puesto. Los primeros 2 se etiquetan
    "Semifinales" y el 3º "Tercer puesto" automáticamente.
 
    Con filtro_fase el filtro manual tiene prioridad total.
    """
 
    def _tiene_resultado(fase_txt: str) -> bool:
        if not matches_actuales:
            return False
        return any(
            m.get("fase") == fase_txt and m.get("gf_local") is not None
            for m in matches_actuales
        )
 
    if filtro_fase:
        filtro_norm = filtro_fase.lower()
        fases = [f for f in FASES_ELIMINACION
                 if filtro_norm in f["fase_txt"].lower()]
    else:
        fases = []
        for fase_info in FASES_ELIMINACION:
            fase_txt = fase_info["fase_txt"]
            prereq   = _PREREQ.get(fase_txt)
            if prereq is None:
                fases.append(fase_info)
            elif _tiene_resultado(prereq):
                fases.append(fase_info)
            else:
                log.info(
                    f"  Saltando '{fase_txt}': "
                    f"'{prereq}' aún sin resultados."
                )
 
    todos = []
    for fase_info in fases:
        fase_txt = fase_info["fase_txt"]
        log.info(f"  Raspando: {fase_txt}")
        partidos = partidos_de_pagina(
            fase_info["pagina"], fase_txt, ""
        )
 
        if fase_txt == "Semifinales":
            # La página de Semifinales incluye también el partido por el
            # tercer puesto (3º y 4º puesto). Wikipedia lo pone al final,
            # tras los 2 partidos de semis. Reétiquetamos a partir del 3º.
            for i, p in enumerate(partidos):
                if i >= 2:
                    p["fase"] = "Tercer puesto"
                    log.info(
                        f"    → Reetiquetado como 'Tercer puesto': "
                        f"{p.get('team1')} vs {p.get('team2')}"
                    )
 
        todos.extend(partidos)
        time.sleep(PAUSA_ENTRE_PAGINAS)
 
    return todos


# ─────────────────────────────────────────────────────────────────────────────
# FUSIÓN CON matches.json
# ─────────────────────────────────────────────────────────────────────────────

def fusionar_en_matches(nuevos: list, matches: list) -> tuple[list, int, int]:
    """Combina los partidos recién leídos de Wikipedia con lo ya guardado.
    Empareja por (equipo local, equipo visitante) sin importar el orden, ya
    que Wikipedia puede listar el mismo cruce como local/visitante distinto
    según la fase. Nunca toca penfall_*/penpar_*."""
    def clave(local, visit):
        return tuple(sorted([local, visit]))
    indice = {clave(m["local"], m["visitante"]): m for m in matches}
    siguiente_id = (max((m["id"] for m in matches), default=0)) + 1
    nuevos_insertados = 0
    actualizados = 0
    for p in nuevos:
        k = clave(p["team1"], p["team2"])
        existente = indice.get(k)
        if existente is None:
            m = {
                "id": siguiente_id,
                "fecha": p["fecha"],
                "fase": p["fase"],
                "grupo": p["grupo"],
                "match_num": p.get("match_num"),          # ← NUEVO
                "local": p["team1"],
                "gf_local": p["gf1"], "gc_local": p["gf2"],
                "ta_local": p["cards1"]["ta"], "doblea_local": p["cards1"]["doble_a"], "rd_local": p["cards1"]["rd"],
                "penfall_local": 0, "penpar_local": 0,
                "visitante": p["team2"],
                "gf_visit": p["gf2"], "gc_visit": p["gf1"],
                "ta_visit": p["cards2"]["ta"], "doblea_visit": p["cards2"]["doble_a"], "rd_visit": p["cards2"]["rd"],
                "penfall_visit": 0, "penpar_visit": 0,
                "pen_tanda_local": None, "pen_tanda_visit": None,
            }
            matches.append(m)
            indice[k] = m
            siguiente_id += 1
            nuevos_insertados += 1
            log.info(f"  NUEVO  {p['team1']} {p['gf1']}-{p['gf2']} {p['team2']}  [{p['fase']}]")
        else:
            invertido = existente["local"] != p["team1"]
            cambios = []
            def _set(campo, valor):
                if existente.get(campo) != valor:
                    existente[campo] = valor
                    cambios.append(campo)
            _set("fecha", p["fecha"])
            _set("fase", p["fase"])
            _set("grupo", p["grupo"])
            _set("match_num", p.get("match_num"))         # ← NUEVO
            if not invertido:
                _set("gf_local", p["gf1"]); _set("gc_local", p["gf2"])
                _set("ta_local", p["cards1"]["ta"]); _set("doblea_local", p["cards1"]["doble_a"]); _set("rd_local", p["cards1"]["rd"])
                _set("gf_visit", p["gf2"]); _set("gc_visit", p["gf1"])
                _set("ta_visit", p["cards2"]["ta"]); _set("doblea_visit", p["cards2"]["doble_a"]); _set("rd_visit", p["cards2"]["rd"])
            else:
                _set("gf_local", p["gf2"]); _set("gc_local", p["gf1"])
                _set("ta_local", p["cards2"]["ta"]); _set("doblea_local", p["cards2"]["doble_a"]); _set("rd_local", p["cards2"]["rd"])
                _set("gf_visit", p["gf1"]); _set("gc_visit", p["gf2"])
                _set("ta_visit", p["cards1"]["ta"]); _set("doblea_visit", p["cards1"]["doble_a"]); _set("rd_visit", p["cards1"]["rd"])
            # penfall_*/penpar_* NUNCA se tocan aquí (se quedan con lo que ya
            # hubiera, manual). Si la fila es nueva, ya se crearon a 0 arriba.
            if cambios:
                actualizados += 1
                log.info(f"  UPD    {existente['local']} vs {existente['visitante']} -> {', '.join(cambios)}")
    return matches, nuevos_insertados, actualizados


# ─────────────────────────────────────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Actualizador Mundial 2026 (versión nube, sin Excel/Windows)"
    )
    parser.add_argument(
        "--fase", default=None,
        help=(
            "grupos | eliminacion | dieciseisavos | octavos "
            "| cuartos | semifinales | final"
        ),
    )
    parser.add_argument("--grupo", default=None, help="Letra de grupo (A-L)")
    args = parser.parse_args()
 
    log.info("=" * 60)
    log.info("MUNDIAL 2026 · BOLILLA — actualización")
    log.info("=" * 60)
 
    fase_arg  = args.fase.lower()  if args.fase  else None
    grupo_arg = args.grupo.upper() if args.grupo else None
 
    # Cargar matches ANTES de decidir qué fases eliminar raspar
    matches = core.cargar_json(MATCHES_PATH, [])
    log.info(f"Partidos en matches.json al arrancar: {len(matches)}")
 
    nuevos = []
 
    if grupo_arg:
        log.info(f"Modo: Grupo {grupo_arg}")
        nuevos = procesar_grupos(filtro_grupo=grupo_arg)
 
    elif fase_arg in (None, "grupos"):
        log.info("Modo: Fase de Grupos (A-L)")
        nuevos += procesar_grupos()
        if fase_arg is None:
            log.info("Modo: Fases Eliminatorias (con lógica de umbral)")
            nuevos += procesar_eliminacion(matches_actuales=matches)
 
    elif fase_arg == "eliminacion":
        nuevos += procesar_eliminacion(matches_actuales=matches)
 
    else:
        # Filtro manual: sin umbral
        nuevos += procesar_eliminacion(filtro_fase=fase_arg)
 
    if nuevos:
        log.info(f"Total partidos leídos de Wikipedia: {len(nuevos)}")
        matches, n_nuevos, n_act = fusionar_en_matches(nuevos, matches)
        core.guardar_json(MATCHES_PATH, matches)
        log.info(f"Partidos NUEVOS insertados: {n_nuevos}")
        log.info(f"Partidos actualizados:      {n_act}")
    else:
        log.info(
            "Wikipedia no devolvió partidos nuevos. "
            "Se regenera data.json por si hay cambios manuales."
        )
 
    data = core.construir_y_guardar(MATCHES_PATH, MANUAL_PATH, SALIDA_PATH)
    log.info(
        f"data.json regenerado. "
        f"Partidos jugados: {data['meta']['total_partidos_jugados']}"
    )
    log.info("✔ Proceso completado.")
 
 
if __name__ == "__main__":
    main()
