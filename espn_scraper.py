# -*- coding: utf-8 -*-
"""
espn_scraper.py — Mundial 2026 · Bolilla
===========================================
Scraper de la API pública de ESPN (sin clave), usado como SEGUNDA FUENTE
para comprobar/complementar lo que se lee de Wikipedia en
actualizar_mundial.py. Mantiene toda la lógica de parseo de eventos
(goles/tarjetas/penaltis) del scraper original (mundial_scraper.py),
pero añade una capa de agregación (`obtener_partidos_resumen`) que
devuelve los datos ya en el mismo formato de campos que matches.json,
para que conciliacion.py pueda comparar partido a partido sin tener
que entender la estructura cruda de ESPN.

Pensado para llamarse solo con las fechas que realmente hacen falta
(las de partidos aún no verificados, ver conciliacion.py), nunca con
"todo el torneo" en cada ejecución — así no se machaca la API de ESPN
ni se ralentiza el workflow.
"""
from __future__ import annotations

import time
import logging
import re as _re
from datetime import date, datetime, timedelta

import requests

from nombres_equipos import traducir

log = logging.getLogger(__name__)

ESPN_LEAGUE = "fifa.world"
ESPN_BASE_URL = "https://site.api.espn.com/apis/site/v2/sports/soccer"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/125.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json",
}

PAUSA_ENTRE_PETICIONES = 1.2
REINTENTOS = 3
TIMEOUT = 15

FECHA_INICIO_MUNDIAL = date(2026, 6, 11)
FECHA_FIN_MUNDIAL = date(2026, 7, 19)


# ─────────────────────────────────────────────────────────────────────────────
# RED
# ─────────────────────────────────────────────────────────────────────────────

def _get(url: str, params: dict | None = None) -> dict | None:
    for intento in range(1, REINTENTOS + 1):
        try:
            r = requests.get(url, headers=HEADERS, params=params, timeout=TIMEOUT)
            r.raise_for_status()
            return r.json()
        except requests.HTTPError as e:
            log.warning(f"[ESPN] HTTP error en {url} (intento {intento}/{REINTENTOS}): {e}")
        except requests.RequestException as e:
            log.warning(f"[ESPN] Error de red en {url} (intento {intento}/{REINTENTOS}): {e}")
        if intento < REINTENTOS:
            time.sleep(2 ** intento)
    log.error(f"[ESPN] Fallo definitivo al obtener: {url}")
    return None


# ─────────────────────────────────────────────────────────────────────────────
# PARTIDOS POR FECHA
# ─────────────────────────────────────────────────────────────────────────────

def obtener_partidos_del_dia(fecha: date) -> list[dict]:
    fecha_str = fecha.strftime("%Y%m%d")
    url = f"{ESPN_BASE_URL}/{ESPN_LEAGUE}/scoreboard"
    datos = _get(url, params={"dates": fecha_str, "limit": 50})
    if not datos:
        return []
    partidos = []
    for evento in datos.get("events", []):
        p = _parsear_evento(evento)
        if p:
            partidos.append(p)
    return partidos


def _parsear_evento(evento: dict) -> dict | None:
    try:
        eid = evento.get("id")
        if not eid:
            return None
        comp = (evento.get("competitions") or [{}])[0]
        competidores = comp.get("competitors", [])
        local = next((c for c in competidores if c.get("homeAway") == "home"), {})
        visitante = next((c for c in competidores if c.get("homeAway") == "away"), {})
        status = evento.get("status", {})
        local_score = local.get("score")
        visit_score = visitante.get("score")
        return {
            "id": eid,
            "fecha_utc": evento.get("date", ""),
            "local_raw": local.get("team", {}).get("displayName", ""),
            "visitante_raw": visitante.get("team", {}).get("displayName", ""),
            "goles_local": int(local_score) if local_score not in (None, "") else None,
            "goles_visit": int(visit_score) if visit_score not in (None, "") else None,
            "completado": status.get("type", {}).get("completed", False),
        }
    except Exception as e:
        log.error(f"[ESPN] Error al parsear evento {evento.get('id')}: {e}")
        return None


# ─────────────────────────────────────────────────────────────────────────────
# DETALLES (goles / tarjetas / penaltis) — idéntico al scraper original
# ─────────────────────────────────────────────────────────────────────────────

_IDS_IGNORAR = {"76", "80", "81", "82", "83", "84", "85", "129", "130",
                "86", "87", "88", "89", "90", "91"}
_IDS_GOL = {"70", "112"}
_IDS_AUTOGOL = {"71"}
_ID_AMARILLA = "94"
_ID_ROJA = "95"
_ID_2AMARILLA = "96"
_IDS_PEN_FALL = {"113", "114"}
_IDS_TANDA_GOL = {"108", "109"}
_IDS_TANDA_FALL = {"110", "111"}

_TXT_GOL = {"goal"}
_TXT_AUTOGOL = {"own goal"}
_TXT_AMARILLA = {"yellow card"}
_TXT_ROJA = {"red card"}
_TXT_2AMARILLA = {"yellow red card", "second yellow"}
_TXT_PEN_FALL = {"penalty - missed", "penalty missed", "penalty saved", "penalty - saved"}
_TXT_TANDA_GOL = {"penalty - goal", "penalty goal"}
_TXT_TANDA_FALL = {"penalty - missed shootout", "penalty shootout missed"}


def obtener_detalles_partido(partido_id: str) -> dict:
    url = f"{ESPN_BASE_URL}/{ESPN_LEAGUE}/summary"
    datos = _get(url, params={"event": partido_id})
    detalles = {"goles": [], "tarjetas": [], "penaltis_fallados": [], "tanda_penaltis": []}
    if not datos:
        return detalles
    eventos = datos.get("keyEvents", [])
    if not eventos:
        comp = (datos.get("header", {}).get("competitions") or [{}])[0]
        eventos = comp.get("details", [])
    for ev in eventos:
        type_id = str(ev.get("type", {}).get("id") or "")
        type_text = (ev.get("type", {}).get("text") or "").lower().strip()
        periodo_n = ev.get("period", {}).get("number", 1)
        minuto = ev.get("clock", {}).get("displayValue", "?")
        equipo_raw = (ev.get("team") or {}).get("displayName", "")
        jugador = _extraer_jugador(ev)

        es_scoring = bool(ev.get("scoringPlay", False))
        es_penalti = bool(ev.get("penaltyKick", False))
        es_autogol = bool(ev.get("ownGoal", False))
        es_tanda = bool(ev.get("shootout", False))

        if type_id in _IDS_IGNORAR:
            continue

        if es_tanda or periodo_n == 5:
            if es_scoring or type_id in _IDS_TANDA_GOL or any(t in type_text for t in _TXT_TANDA_GOL):
                resultado = "Gol"
            elif type_id in _IDS_TANDA_FALL or any(t in type_text for t in _TXT_TANDA_FALL) \
                    or "missed" in type_text or "saved" in type_text:
                resultado = _motivo_penalti(type_text)
            else:
                continue
            detalles["tanda_penaltis"].append({
                "jugador": jugador, "equipo_raw": equipo_raw, "resultado": resultado,
            })
            continue

        es_gol = (
            type_id in _IDS_GOL or type_id in _IDS_AUTOGOL or es_scoring
            or (type_text in _TXT_GOL or type_text in _TXT_AUTOGOL)
        )
        if es_gol and periodo_n <= 4:
            detalles["goles"].append({
                "minuto": minuto, "jugador": jugador, "equipo_raw": equipo_raw,
                "tipo": _clasificar_gol(es_autogol, es_penalti, type_text),
            })
            continue

        if type_id == _ID_2AMARILLA or any(t in type_text for t in _TXT_2AMARILLA):
            detalles["tarjetas"].append(_tarjeta(minuto, jugador, equipo_raw, "2ª Amarilla → Roja"))
        elif type_id == _ID_ROJA or any(t in type_text for t in _TXT_ROJA):
            detalles["tarjetas"].append(_tarjeta(minuto, jugador, equipo_raw, "Roja Directa"))
        elif type_id == _ID_AMARILLA or any(t in type_text for t in _TXT_AMARILLA):
            detalles["tarjetas"].append(_tarjeta(minuto, jugador, equipo_raw, "Amarilla"))
        elif periodo_n <= 4 and (type_id in _IDS_PEN_FALL or any(t in type_text for t in _TXT_PEN_FALL)):
            detalles["penaltis_fallados"].append({
                "minuto": minuto, "jugador": jugador, "equipo_raw": equipo_raw,
                "motivo": _motivo_penalti(type_text),
            })
    return detalles


def _clasificar_gol(es_autogol, es_penalti, type_text) -> str:
    if es_autogol or "own goal" in type_text:
        return "Autogol"
    if es_penalti or "penalty" in type_text:
        return "Penalti"
    return "Gol"


def _extraer_jugador(evento: dict) -> str:
    for p in (evento.get("participants") or []):
        nombre = (p.get("athlete") or {}).get("displayName", "")
        if nombre:
            return nombre
    for a in (evento.get("athletesInvolved") or []):
        if a.get("displayName"):
            return a["displayName"]
    atleta = evento.get("athlete") or {}
    return atleta.get("displayName", "")


def _tarjeta(minuto, jugador, equipo_raw, tipo) -> dict:
    return {"minuto": minuto, "jugador": jugador, "equipo_raw": equipo_raw, "tipo": tipo}


def _motivo_penalti(type_text: str) -> str:
    t = type_text.lower()
    if "saved" in t or "keeper" in t or "parad" in t:
        return "Parado por portero"
    if "wide" in t or "over" in t or "high" in t or "missed" in t:
        return "Fuera"
    if "post" in t or "bar" in t or "crossbar" in t or "palo" in t:
        return "Al palo / Larguero"
    return "Fallado"


# ─────────────────────────────────────────────────────────────────────────────
# AGREGACIÓN A NIVEL DE PARTIDO (lo que consume conciliacion.py)
# ─────────────────────────────────────────────────────────────────────────────

def _agregar_partido(base: dict, detalles: dict) -> dict:
    """Convierte el partido crudo de ESPN (+ sus eventos) en un dict con
    el mismo esquema de campos que usa matches.json, ya con los nombres
    de equipo traducidos al español canónico."""
    local = traducir(base["local_raw"])
    visit = traducir(base["visitante_raw"])

    def lado(equipo_raw):
        return "local" if traducir(equipo_raw) == local else (
            "visit" if traducir(equipo_raw) == visit else None
        )

    ta_l = ta_v = da_l = da_v = rd_l = rd_v = 0
    for t in detalles["tarjetas"]:
        l = lado(t["equipo_raw"])
        if l is None:
            continue
        if t["tipo"] == "Amarilla":
            ta_l += (l == "local"); ta_v += (l == "visit")
        elif t["tipo"] == "2ª Amarilla → Roja":
            da_l += (l == "local"); da_v += (l == "visit")
        elif t["tipo"] == "Roja Directa":
            rd_l += (l == "local"); rd_v += (l == "visit")

    penfall_l = penfall_v = penpar_l = penpar_v = 0
    for pf in detalles["penaltis_fallados"]:
        l = lado(pf["equipo_raw"])
        if l is None:
            continue
        # El que falla el penalti suma "fallado" (sea cual sea el motivo)
        penfall_l += (l == "local"); penfall_v += (l == "visit")
        # Todo penalti fallado cuenta como "parado" para el equipo contrario,
        # sea cual sea el motivo (fuera, palo o parada del portero)
        penpar_l += (l == "visit"); penpar_v += (l == "local")

    pen_tanda_l = pen_tanda_v = None
    if detalles["tanda_penaltis"]:
        pen_tanda_l = pen_tanda_v = 0
        for tp in detalles["tanda_penaltis"]:
            l = lado(tp["equipo_raw"])
            if l is None or tp["resultado"] != "Gol":
                continue
            pen_tanda_l += (l == "local"); pen_tanda_v += (l == "visit")

    goleadores = []
    for g in detalles["goles"]:
        if g["tipo"] == "Autogol":
            continue  # un autogol no cuenta para la tabla de máximo goleador
        l = lado(g["equipo_raw"])
        equipo = local if l == "local" else (visit if l == "visit" else traducir(g["equipo_raw"]))
        goleadores.append({
            "jugador": g["jugador"], "equipo": equipo,
            "minuto": g["minuto"], "tipo": g["tipo"],
        })

    return {
        "espn_id": base["id"],
        "fecha": base["fecha_utc"][:10] if base["fecha_utc"] else None,
        "local": local, "visitante": visit,
        "gf_local": base["goles_local"], "gf_visit": base["goles_visit"],
        "ta_local": ta_l, "doblea_local": da_l, "rd_local": rd_l,
        "ta_visit": ta_v, "doblea_visit": da_v, "rd_visit": rd_v,
        "penfall_local": penfall_l, "penpar_local": penpar_l,
        "penfall_visit": penfall_v, "penpar_visit": penpar_v,
        "pen_tanda_local": pen_tanda_l, "pen_tanda_visit": pen_tanda_v,
        "completado": base["completado"],
        "goleadores": goleadores,
    }


def obtener_partidos_resumen(fechas: set[date]) -> list[dict]:
    """Punto de entrada usado por el orquestador (actualizar_mundial.py).
    Recibe SOLO el conjunto de fechas que realmente hace falta consultar
    (las de partidos pendientes de verificar — ver conciliacion.py) y
    devuelve la lista de partidos completados de ESPN en esas fechas, ya
    agregados al esquema de matches.json. No recorre nunca todo el
    torneo: quien decide qué fechas pedir es quien llama a esta función."""
    fechas = sorted(fechas)
    if not fechas:
        return []
    log.info(f"[ESPN] Consultando {len(fechas)} fecha(s): {', '.join(f.isoformat() for f in fechas)}")

    crudos = {}
    for fecha in fechas:
        for p in obtener_partidos_del_dia(fecha):
            crudos[p["id"]] = p
        time.sleep(PAUSA_ENTRE_PETICIONES)

    resumenes = []
    completados = [p for p in crudos.values() if p["completado"]]
    log.info(f"[ESPN] Partidos completados encontrados: {len(completados)}")
    for p in completados:
        detalles = obtener_detalles_partido(p["id"])
        resumenes.append(_agregar_partido(p, detalles))
        time.sleep(PAUSA_ENTRE_PETICIONES)
    return resumenes
