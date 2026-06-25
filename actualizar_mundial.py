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
import unicodedata
import datetime as _dt
from pathlib import Path

import requests

import mundial_core as core
from nombres_equipos import NOMBRE_MAP, traducir
import conciliacion as conc
import espn_scraper as espn
import goleadores as gol

BASE_DIR = Path(__file__).parent
MATCHES_PATH = BASE_DIR / "matches.json"
MANUAL_PATH = BASE_DIR / "manual_overrides.json"
SALIDA_PATH = BASE_DIR / "docs" / "data.json"
LOG_PATH = BASE_DIR / "log_mundial.txt"
ESTADO_PATH = BASE_DIR / "estado_reconciliacion.json"
DISCREPANCIAS_PATH = BASE_DIR / "discrepancias.json"
GOLEADORES_PATH = BASE_DIR / "goleadores_por_partido.json"

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

# NOMBRE_MAP y traducir() viven ahora en nombres_equipos.py (importado arriba)
# para poder reutilizarlos también desde espn_scraper.py.

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


# ─────────────────────────────────────────────────────────────────────────────
# ESTADIOS — identificación canónica de sede
# ─────────────────────────────────────────────────────────────────────────────
# Wikipedia puede referirse a cada estadio de varias formas distintas:
#   - Con el nombre comercial habitual (p.ej. "SoFi Stadium").
#   - Con el nombre alternativo sin patrocinio que impone la FIFA durante el
#     torneo (p.ej. "Estadio de Los Ángeles" / "Los Angeles Stadium"), tal
#     y como advierte la propia Wikipedia: "Debido a las normas de la FIFA
#     sobre el patrocinio de estadios, las sedes utilizan nombres
#     alternativos durante el torneo".
#   - Solo con la ciudad/área metropolitana, en el campo "ciudad".
# Como cada una de las 16 sedes del Mundial 2026 está en una ciudad/área
# distinta, basta con detectar CUALQUIERA de los alias (nombre comercial,
# nombre FIFA o ciudad) para identificar la sede de forma inequívoca.
#
# Las claves de este diccionario (p.ej. "boston", "dallas"...) son los
# identificadores internos de estadio usados en _MATCH_NUM_CALENDAR.
# ─────────────────────────────────────────────────────────────────────────────

_ESTADIOS_ALIASES_RAW: dict[str, list[str]] = {
    "boston":   ["Gillette Stadium", "Estadio de Boston", "Boston Stadium",
                 "Foxborough", "Boston"],
    "nynj":     ["MetLife Stadium", "Estadio de Nueva York Nueva Jersey",
                 "New York New Jersey Stadium", "East Rutherford",
                 "Nueva York/Nueva Jersey", "Nueva Jersey"],
    "la":       ["SoFi Stadium", "Estadio de Los Ángeles", "Los Angeles Stadium",
                 "Inglewood", "Los Ángeles"],
    "monterrey": ["Estadio BBVA", "Estadio Monterrey", "Monterrey"],
    "toronto":  ["BMO Field", "Estadio de Toronto", "Toronto Stadium", "Toronto"],
    "bayarea":  ["Levi's Stadium", "Levis Stadium",
                 "Estadio del Área de la Bahía de San Francisco",
                 "San Francisco Bay Area Stadium", "Santa Clara",
                 "Bay Area", "San Francisco"],
    "seattle":  ["Lumen Field", "Estadio de Seattle", "Seattle Stadium", "Seattle"],
    "houston":  ["NRG Stadium", "Estadio de Houston", "Houston Stadium", "Houston"],
    "dallas":   ["AT&T Stadium", "Estadio de Dallas", "Dallas Stadium",
                 "Arlington", "Dallas"],
    "cdmx":     ["Estadio Azteca", "Estadio Ciudad de México",
                 "Mexico City Stadium", "Ciudad de México"],
    "atlanta":  ["Mercedes-Benz Stadium", "Estadio de Atlanta",
                 "Atlanta Stadium", "Atlanta"],
    "miami":    ["Hard Rock Stadium", "Estadio de Miami", "Miami Stadium",
                 "Miami Gardens", "Miami"],
    "vancouver": ["BC Place", "Estadio de Vancouver", "Vancouver Stadium", "Vancouver"],
    "kc":       ["GEHA Field at Arrowhead Stadium", "Arrowhead Stadium",
                 "Estadio de Kansas City", "Kansas City Stadium", "Kansas City"],
    "philly":   ["Lincoln Financial Field", "Estadio de Filadelfia",
                 "Philadelphia Stadium", "Filadelfia", "Philadelphia"],
}


def _normalizar(s: str) -> str:
    """minúsculas, sin acentos, sin puntuación — para comparar a prueba de
    variaciones de tipeo/formato entre Wikipedia y nuestras tablas."""
    if not s:
        return ""
    s = s.lower()
    s = unicodedata.normalize("NFKD", s)
    s = "".join(c for c in s if not unicodedata.combining(c))
    s = re.sub(r"[^a-z0-9]+", " ", s)
    return s.strip()


# Alias ya normalizados, ordenados de más largo a más corto para que al
# buscar coincidencias se prefiera siempre el alias más específico (p.ej.
# "sofi stadium" antes que el genérico "los angeles" si ambos aparecieran).
_ESTADIOS_ALIASES: dict[str, list[str]] = {
    eid: sorted({_normalizar(a) for a in aliases}, key=len, reverse=True)
    for eid, aliases in _ESTADIOS_ALIASES_RAW.items()
}


def _detectar_estadio_id(estadio_raw: str, ciudad_raw: str = "") -> str | None:
    """Identifica la sede (uno de los 16 identificadores internos) a partir
    del texto de los campos 'estadio'/'sede' y 'ciudad' tal como vienen del
    wikitext. Devuelve None si no se reconoce ninguno de los alias."""
    texto = _normalizar(f"{estadio_raw} {ciudad_raw}")
    if not texto:
        return None
    mejor_id, mejor_len = None, 0
    for eid, aliases in _ESTADIOS_ALIASES.items():
        for alias in aliases:
            if alias and alias in texto and len(alias) > mejor_len:
                mejor_id, mejor_len = eid, len(alias)
    return mejor_id


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
    #if gf1 is None or gf2 is None:
    #    return None

    fecha_raw = _campo(bloque, "fecha") or _campo(bloque, "date") or ""
    m_tpl_fecha = re.search(r"\{\{\s*fecha\s*\|\s*(\d{1,2})(?:\s*\|\s*(\d{1,2}))?(?:\s*\|\s*(\d{4}))?", fecha_raw, re.IGNORECASE)
    if m_tpl_fecha:
        dia = int(m_tpl_fecha.group(1))
        mes = int(m_tpl_fecha.group(2)) if m_tpl_fecha.group(2) else 1
        anio = int(m_tpl_fecha.group(3)) if m_tpl_fecha.group(3) else 2026
        fecha = f"{anio}-{mes:02d}-{dia:02d}"
    else:
        MESES = {"enero": 1, "febrero": 2, "marzo": 3, "abril": 4, "mayo": 5, "junio": 6,
                "julio": 7, "agosto": 8, "septiembre": 9, "octubre": 10, "noviembre": 11, "diciembre": 12}
        m_fecha2 = re.search(r"(\d{1,2})\s+de\s+(\w+)(?:\s+de\s+(\d{4}))?", fecha_raw, re.IGNORECASE)
        if m_fecha2:
            dia = int(m_fecha2.group(1))
            mes = MESES.get(m_fecha2.group(2).lower(), 0)
            anio = int(m_fecha2.group(3)) if m_fecha2.group(3) else 2026
            
            fecha = f"{anio}-{str(mes).zfill(2)}-{str(dia).zfill(2)}" if mes else ""
        else:
            fecha = ""

    cards1, cards2 = extraer_tarjetas_desde_bloque(bloque)

    # ── Estadio / sede del partido ──────────────────────────────────────
    # Necesario para asignar match_num en fases eliminatorias (ver
    # _asignar_match_num): el estadio es mucho más fiable que el orden
    # cronológico, porque Wikipedia no siempre lista los partidos de una
    # fase en el orden en que se juegan.
    estadio_raw = (_campo(bloque, "estadio") or _campo(bloque, "sede")
                   or _campo(bloque, "venue") or _campo(bloque, "stadium") or "")
    ciudad_raw = (_campo(bloque, "ciudad") or _campo(bloque, "city")
                  or _campo(bloque, "ubicación") or _campo(bloque, "ubicacion")
                  or _campo(bloque, "location") or "")
    estadio_raw = _limpiar_plantillas(estadio_raw)
    ciudad_raw = _limpiar_plantillas(ciudad_raw)
    estadio_id = _detectar_estadio_id(estadio_raw, ciudad_raw)

    return {
        "team1": t1, "team2": t2, "fecha": fecha, "gf1": gf1, "gf2": gf2,
        "cards1": cards1, "cards2": cards2, "fase": fase_txt, "grupo": grupo_letra,
        "estadio_raw": estadio_raw, "ciudad_raw": ciudad_raw, "estadio_id": estadio_id,
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
# CALENDARIO CANÓNICO DE match_num — fuente de verdad única
# ─────────────────────────────────────────────────────────────────────────────
# Cambio de criterio (antes: fecha+hora / equipos / fecha+orden):
#
# En las fases eliminatorias los partidos NO siempre aparecen en Wikipedia
# en orden cronológico, así que ni "orden de aparición" ni "equipos en ese
# momento" (que dependen de quién haya clasificado) son fiables para
# determinar el match_num oficial FIFA. Lo que SÍ es fiable es la sede:
# cada partido del Mundial 2026 se juega en un estadio distinto, así que
# (fecha, estadio) identifica un partido sin ambigüedad.
#
# Estrategias en orden de prioridad:
#   1. (fase, fecha exacta, estadio) → determinista al 100 %.
#   2. (fase, estadio) único en esa fase → si esa sede solo se usa una vez
#      en la fase, no hace falta ni la fecha (cubre errores de fecha,
#      incluido el caso típico de que la hora esté mal y caiga un día
#      antes/después por el cambio de zona horaria).
#   3. (fase, estadio) con varias fechas → se elige la fecha más cercana a
#      la que trae Wikipedia (cubre el caso "falla la fecha por un día").
#   4. Frozenset de equipos → fallback legado, útil sobre todo en
#      Dieciseisavos cuando los cruces ya tienen equipos reales.
#   5. Fecha sola + orden de aparición → último recurso, si ni el estadio
#      ni los equipos se pudieron identificar.
# ─────────────────────────────────────────────────────────────────────────────

_MATCH_NUM_CALENDAR: list[dict] = [
    # ── Dieciseisavos de final ─────────────────────────────────────────────
    {"mn": 73,  "fecha": "2026-06-28", "fase": "Dieciseisavos de final", "estadio": "la"},
    {"mn": 74,  "fecha": "2026-06-29", "fase": "Dieciseisavos de final", "estadio": "boston"},
    {"mn": 75,  "fecha": "2026-06-30", "fase": "Dieciseisavos de final", "estadio": "monterrey"},
    {"mn": 76,  "fecha": "2026-06-29", "fase": "Dieciseisavos de final", "estadio": "houston"},
    {"mn": 77,  "fecha": "2026-06-30", "fase": "Dieciseisavos de final", "estadio": "nynj"},
    {"mn": 78,  "fecha": "2026-06-30", "fase": "Dieciseisavos de final", "estadio": "dallas"},
    {"mn": 79,  "fecha": "2026-07-01", "fase": "Dieciseisavos de final", "estadio": "cdmx"},
    {"mn": 80,  "fecha": "2026-07-01", "fase": "Dieciseisavos de final", "estadio": "atlanta"},
    {"mn": 81,  "fecha": "2026-07-02", "fase": "Dieciseisavos de final", "estadio": "bayarea"},
    {"mn": 82,  "fecha": "2026-07-01", "fase": "Dieciseisavos de final", "estadio": "seattle"},
    {"mn": 83,  "fecha": "2026-07-03", "fase": "Dieciseisavos de final", "estadio": "toronto"},
    {"mn": 84,  "fecha": "2026-07-02", "fase": "Dieciseisavos de final", "estadio": "la"},
    {"mn": 85,  "fecha": "2026-07-03", "fase": "Dieciseisavos de final", "estadio": "vancouver"},
    {"mn": 86,  "fecha": "2026-07-03", "fase": "Dieciseisavos de final", "estadio": "miami"},
    {"mn": 87,  "fecha": "2026-07-04", "fase": "Dieciseisavos de final", "estadio": "kc"},
    {"mn": 88,  "fecha": "2026-07-03", "fase": "Dieciseisavos de final", "estadio": "dallas"},
    # ── Octavos de final ───────────────────────────────────────────────────
    {"mn": 89,  "fecha": "2026-07-04", "fase": "Octavos de final", "estadio": "philly"},
    {"mn": 90,  "fecha": "2026-07-04", "fase": "Octavos de final", "estadio": "houston"},
    {"mn": 91,  "fecha": "2026-07-05", "fase": "Octavos de final", "estadio": "nynj"},
    {"mn": 92,  "fecha": "2026-07-06", "fase": "Octavos de final", "estadio": "cdmx"},
    {"mn": 93,  "fecha": "2026-07-06", "fase": "Octavos de final", "estadio": "dallas"},
    {"mn": 94,  "fecha": "2026-07-07", "fase": "Octavos de final", "estadio": "seattle"},
    {"mn": 95,  "fecha": "2026-07-07", "fase": "Octavos de final", "estadio": "atlanta"},
    {"mn": 96,  "fecha": "2026-07-07", "fase": "Octavos de final", "estadio": "vancouver"},
    # ── Cuartos de final ───────────────────────────────────────────────────
    {"mn": 97,  "fecha": "2026-07-09", "fase": "Cuartos de final", "estadio": "boston"},
    {"mn": 98,  "fecha": "2026-07-10", "fase": "Cuartos de final", "estadio": "la"},
    {"mn": 99,  "fecha": "2026-07-11", "fase": "Cuartos de final", "estadio": "miami"},
    {"mn": 100, "fecha": "2026-07-12", "fase": "Cuartos de final", "estadio": "kc"},
    # ── Semifinales ────────────────────────────────────────────────────────
    {"mn": 101, "fecha": "2026-07-14", "fase": "Semifinales", "estadio": "dallas"},
    {"mn": 102, "fecha": "2026-07-15", "fase": "Semifinales", "estadio": "atlanta"},
    # ── Tercer puesto ──────────────────────────────────────────────────────
    {"mn": 103, "fecha": "2026-07-18", "fase": "Tercer puesto", "estadio": "miami"},
    # ── Final ──────────────────────────────────────────────────────────────
    {"mn": 104, "fecha": "2026-07-19", "fase": "Final", "estadio": "nynj"},
]

# ── Índices derivados (se construyen una sola vez al cargar el módulo) ─────


def _fecha_a_obj(fecha: str):
    try:
        return _dt.date.fromisoformat(fecha)
    except (ValueError, TypeError):
        return None


# Estrategia 1: (fase, fecha, estadio) → match_num exacto
_MN_BY_FASE_FECHA_ESTADIO: dict[tuple[str, str, str], int] = {
    (e["fase"], e["fecha"], e["estadio"]): e["mn"]
    for e in _MATCH_NUM_CALENDAR
}

# Estrategias 2 y 3: (fase, estadio) → lista de (fecha, match_num)
_MN_BY_FASE_ESTADIO: dict[tuple[str, str], list[tuple[str, int]]] = {}
for _e in _MATCH_NUM_CALENDAR:
    _MN_BY_FASE_ESTADIO.setdefault((_e["fase"], _e["estadio"]), []).append((_e["fecha"], _e["mn"]))

# Estrategia 4: frozenset de equipos → match_num (solo será útil si el
# llamador nos pasa equipos ya identificados de cruces concretos; se
# mantiene vacío por defecto y se puede rellenar si se desea reactivar).
_MN_BY_TEAMS: dict[frozenset, int] = {}

# Estrategia 5: (fase, fecha) sola → lista de match_num en el orden del
# calendario oficial (no del orden en que aparezcan en Wikipedia).
_MN_BY_FASE_FECHA: dict[tuple[str, str], list[int]] = {}
for _e in _MATCH_NUM_CALENDAR:
    _MN_BY_FASE_FECHA.setdefault((_e["fase"], _e["fecha"]), []).append(_e["mn"])

# Fases con match_num (todas las eliminatorias)
_FASES_CON_MATCH_NUM: set[str] = {
    "Dieciseisavos de final", "Octavos de final", "Cuartos de final",
    "Semifinales", "Tercer puesto", "Final",
}


def _asignar_match_num(p: dict, _usados_por_fecha: dict) -> int | None:
    """Devuelve el match_num correcto para un partido de fase eliminatoria.

    Prioridad (ver cabecera de _MATCH_NUM_CALENDAR para el detalle):
      1. (fase, fecha, estadio) exacto.
      2. (fase, estadio) único en la fase → ignora la fecha.
      3. (fase, estadio) con varias fechas → la más cercana a la de Wikipedia.
      4. Frozenset de equipos (fallback legado).
      5. (fase, fecha) sola + orden de aparición (último recurso).
    """
    fase = p.get("fase")
    if fase not in _FASES_CON_MATCH_NUM:
        return None

    fecha = p.get("fecha") or ""
    estadio_id = p.get("estadio_id")

    # Estrategia 1: fase + fecha + estadio ─────────────────────────────────
    if estadio_id and fecha:
        mn = _MN_BY_FASE_FECHA_ESTADIO.get((fase, fecha, estadio_id))
        if mn is not None:
            return mn

    # Estrategias 2 y 3: fase + estadio (con o sin fecha exacta) ───────────
    if estadio_id:
        candidatos = _MN_BY_FASE_ESTADIO.get((fase, estadio_id), [])
        if len(candidatos) == 1:
            # Esa sede solo se usa una vez en esta fase: no hace falta
            # ni que la fecha coincida (cubre errores de fecha/hora).
            return candidatos[0][1]
        elif len(candidatos) > 1:
            fecha_obj = _fecha_a_obj(fecha)
            if fecha_obj is not None:
                # Elegir la fecha más cercana (cubre desfases de ±1 día
                # típicos de errores de zona horaria en la hora del partido).
                mejor_mn, mejor_dist = None, None
                for fecha_cand, mn_cand in candidatos:
                    obj_cand = _fecha_a_obj(fecha_cand)
                    if obj_cand is None:
                        continue
                    dist = abs((obj_cand - fecha_obj).days)
                    if mejor_dist is None or dist < mejor_dist:
                        mejor_mn, mejor_dist = mn_cand, dist
                if mejor_mn is not None:
                    return mejor_mn
            # Sin fecha utilizable y más de un candidato: no se puede
            # desambiguar solo con el estadio, se sigue con el resto de
            # estrategias.

    # Estrategia 4: frozenset de equipos (fallback legado) ─────────────────
    if p.get("team1") and p.get("team2"):
        mn = _MN_BY_TEAMS.get(frozenset({p["team1"], p["team2"]}))
        if mn is not None:
            return mn

    # Estrategia 5: fase + fecha sola + posición de aparición ──────────────
    if fecha:
        slots = _MN_BY_FASE_FECHA.get((fase, fecha), [])
        clave_uso = (fase, fecha)
        idx = _usados_por_fecha.get(clave_uso, 0)
        if idx < len(slots):
            _usados_por_fecha[clave_uso] = idx + 1
            return slots[idx]

    return None


# ─────────────────────────────────────────────────────────────────────────────
# FUSIÓN CON matches.json

# ─────────────────────────────────────────────────────────────────────────────

# Campos de estadísticas que Wikipedia puede actualizar. Si Wikipedia cambia
# alguno de estos en un partido ya verificado, se desverifica para que la
# siguiente ejecución vuelva a cotejar con ESPN.
_CAMPOS_STATS_WIKI = frozenset({
    "gf_local", "gc_local", "ta_local", "doblea_local", "rd_local",
    "gf_visit", "gc_visit", "ta_visit", "doblea_visit", "rd_visit",
})


def fusionar_en_matches(nuevos: list, matches: list, estado: dict | None = None) -> tuple[list, int, int]:
    """Combina los partidos recién leídos de Wikipedia con lo ya guardado.
    Empareja por (equipo local, equipo visitante) sin importar el orden, ya
    que Wikipedia puede listar el mismo cruce como local/visitante distinto
    según la fase. Nunca toca penfall_*/penpar_*.

    Si se pasa `estado` (estado_reconciliacion.json ya cargado):
      - Nunca sobreescribe campos que estén en `campos_bloqueados` (los que
        el usuario resolvió manualmente con resolver_discrepancia.py).
      - Si Wikipedia cambia un campo de estadísticas en un partido que ya
        estaba "verificado", lo desverifica para forzar una recomprobación
        con ESPN en la siguiente ejecución (en vez de dejar datos inconsistentes).

    Para partidos de fases eliminatorias asigna (y actualiza si falta)
    el campo match_num con el número de partido oficial FIFA del cuadro.
    """

    def clave(local, visit):
        return tuple(sorted([local, visit]))

    indice = {clave(m["local"], m["visitante"]): m for m in matches}
    siguiente_id = (max((m["id"] for m in matches), default=0)) + 1

    nuevos_insertados = 0
    actualizados = 0

    # Contador por fecha: usado por la estrategia-3 de _asignar_match_num
    # (fecha sola + posición de aparición). Se reinicia en cada llamada.
    _usados_por_fecha: dict[tuple, int] = {}

    for p in nuevos:
        # match_num para fases eliminatorias (None si no aplica o no se encuentra)
        match_num = _asignar_match_num(p, _usados_por_fecha)

        if p.get("fase") in _FASES_CON_MATCH_NUM and match_num is None:
            log.warning(
                f"  match_num NO asignado para {p.get('team1')} vs {p.get('team2')} "
                f"[{p.get('fase')}, fecha={p.get('fecha')!r}, "
                f"estadio_raw={p.get('estadio_raw')!r}, estadio_id={p.get('estadio_id')!r}]"
            )

        k = clave(p["team1"], p["team2"])
        existente = indice.get(k)

        if existente is None:
            m = {
                "id": siguiente_id,
                "fecha": p["fecha"],
                "fase": p["fase"],
                "grupo": p["grupo"],
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
            if match_num is not None:
                m["match_num"] = match_num
            matches.append(m)
            indice[k] = m
            siguiente_id += 1
            nuevos_insertados += 1
            log.info(f"  NUEVO  {p['team1']} {p['gf1']}-{p['gf2']} {p['team2']}  [{p['fase']}]"
                     + (f"  match_num={match_num}" if match_num else ""))
        else:
            invertido = existente["local"] != p["team1"]
            cambios = []

            # Clave en el formato de estado_reconciliacion.json
            _clave_est = "|".join(sorted([p["team1"], p["team2"]]))
            _estado_partido = (estado or {}).get(_clave_est, {})
            _bloqueados = frozenset(_estado_partido.get("campos_bloqueados", []))

            def _set(campo, valor):
                # 1. Nunca tocar campos que el usuario bloqueó manualmente.
                if campo in _bloqueados:
                    return
                if existente.get(campo) == valor:
                    return
                existente[campo] = valor
                cambios.append(campo)
                # 2. Si Wikipedia cambia un campo de estadísticas en un partido
                #    ya verificado, lo desverificamos para que la próxima
                #    ejecución vuelva a cotejar esos datos con ESPN.
                if campo in _CAMPOS_STATS_WIKI and estado is not None:
                    if _estado_partido.get("verificado"):
                        _estado_partido["verificado"] = False
                        estado[_clave_est] = _estado_partido  # asegurar escritura en dict
                        log.info(
                            f"  DESVERIFICADO {existente['local']} vs {existente['visitante']}: "
                            f"Wikipedia cambió '{campo}' → se recomprobará con ESPN."
                        )

            _set("fecha", p["fecha"])
            _set("fase", p["fase"])
            _set("grupo", p["grupo"])

            # Asignar match_num si aún no lo tiene (backfill de partidos previos)
            if match_num is not None and existente.get("match_num") is None:
                _set("match_num", match_num)

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
 
    # Cargar matches y estado ANTES de decidir qué fases raspar.
    # El estado se carga aquí (y no más adelante) para que fusionar_en_matches
    # ya pueda consultarlo y respetar los campos bloqueados por el usuario.
    matches = core.cargar_json(MATCHES_PATH, [])
    estado = conc.cargar_estado(ESTADO_PATH)
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
        matches, n_nuevos, n_act = fusionar_en_matches(nuevos, matches, estado)
        core.guardar_json(MATCHES_PATH, matches)
        # Persistir posibles desverificaciones que haya marcado fusionar_en_matches
        conc.guardar_estado(ESTADO_PATH, estado)
        log.info(f"Partidos NUEVOS insertados: {n_nuevos}")
        log.info(f"Partidos actualizados:      {n_act}")
    else:
        log.info(
            "Wikipedia no devolvió partidos nuevos. "
            "Se regenera data.json por si hay cambios manuales."
        )

    # ─────────────────────────────────────────────────────────────────
    # Conciliación con ESPN (segunda fuente)
    # ─────────────────────────────────────────────────────────────────
    # Solo se pide a ESPN lo que de verdad hace falta: las fechas de
    # partidos NO verificados todavía (ver conciliacion.py). Un partido
    # que ya coincidió entre Wikipedia y ESPN se marca "verificado" en
    # estado_reconciliacion.json y no se vuelve a tocar nunca más, así
    # que en ejecuciones sucesivas cada vez se pide menos.
    log.info("-" * 60)
    log.info("Conciliación con ESPN")
    # `estado` ya está cargado desde el inicio de main() (y posiblemente
    # modificado por fusionar_en_matches si Wikipedia cambió algún dato).
    discrepancias = conc.cargar_discrepancias(DISCREPANCIAS_PATH)
    fechas = conc.fechas_pendientes(matches, estado)
    log.info(f"  Fechas a consultar en ESPN: {len(fechas)}")

    try:
        resumenes_espn = espn.obtener_partidos_resumen(fechas)
    except Exception as e:
        log.error(f"  ESPN no disponible esta vez ({e.__class__.__name__}: {e}). "
                  f"Se sigue sin conciliar; se reintentará en la próxima ejecución.")
        resumenes_espn = []

    if resumenes_espn:
        matches, estado, discrepancias, resumen_conc = conc.conciliar(
            matches, resumenes_espn, estado, discrepancias
        )
        core.guardar_json(MATCHES_PATH, matches)
        log.info(
            f"  Verificados nuevos: {resumen_conc['verificados_nuevos']}  ·  "
            f"Discrepancias nuevas: {resumen_conc['discrepancias_nuevas']}  ·  "
            f"Penaltis/tanda aplicados desde ESPN: {resumen_conc['penaltis_aplicados']}  ·  "
            f"ESPN tiene partido y Wikipedia aún no: {resumen_conc['espn_sin_wiki']}"
        )
        if discrepancias:
            log.warning(
                f"  Hay {len(discrepancias)} discrepancia(s) pendientes — revisa "
                f"discrepancias.json y resuélvelas con resolver_discrepancia.py"
            )
        gol.actualizar_goleadores(resumenes_espn, GOLEADORES_PATH)
    else:
        log.info("  ESPN no devolvió partidos completados nuevos para conciliar.")

    conc.guardar_estado(ESTADO_PATH, estado)
    conc.guardar_discrepancias(DISCREPANCIAS_PATH, discrepancias)

    data = core.construir_y_guardar(MATCHES_PATH, MANUAL_PATH, SALIDA_PATH, GOLEADORES_PATH)
    log.info(
        f"data.json regenerado. "
        f"Partidos jugados: {data['meta']['total_partidos_jugados']}"
    )
    log.info("✔ Proceso completado.")
 
 
if __name__ == "__main__":
    main()
