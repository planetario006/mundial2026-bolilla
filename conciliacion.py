# -*- coding: utf-8 -*-
"""
conciliacion.py — Mundial 2026 · Bolilla
===========================================
Compara lo que hay en matches.json (fuente: Wikipedia) con lo que acaba
de leer espn_scraper.py (fuente: ESPN) y decide, partido a partido:
  - Si las dos fuentes coinciden en todo lo comparable  → el partido se
    marca "verificado" en estado_reconciliacion.json y NUNCA se vuelve
    a pedir a ESPN (ni se vuelve a comparar) en ejecuciones futuras.
  - Si ESPN tiene el partido pero Wikipedia todavía no  → se deja
    "pendiente" para reintentar en la siguiente ejecución programada
    (no hace falta ninguna lógica especial de "esperar X horas": como
    el workflow ya corre cada 30 min y aquí solo se vuelve a preguntar
    por los partidos NO verificados, el reintento es automático y barato).
  - Si ambas fuentes tienen el partido pero algún campo no coincide  →
    se anota en discrepancias.json (sin tocar matches.json en ese
    campo) para que el usuario decida a mano con resolver_discrepancia.py.
  - penfall_*/penpar_*/pen_tanda_* (que Wikipedia no trae) se rellenan
    directamente desde ESPN MIENTRAS nadie los haya editado a mano desde
    la última vez; si alguien ya los editó a mano y ESPN dice otra cosa,
    también se anota como discrepancia en vez de pisar la edición manual.

Reintentos de discrepancias pendientes: mientras un partido tenga
alguna discrepancia abierta en discrepancias.json, su fecha se sigue
pidiendo a ESPN en CADA ejecución (sin límite de intentos) — así, si
Wikipedia o ESPN corrigen el dato más adelante, se detecta y el
partido se marca "verificado" automáticamente sin que el usuario
tenga que tocar nada. Si el usuario lo resuelve a mano primero (con
resolver_discrepancia.py bloqueando el campo), deja de comparase ese
campo para siempre.

No hace ninguna llamada de red — solo trabaja con lo que ya se ha
descargado. Quien orquesta las llamadas de red es actualizar_mundial.py.
"""
from __future__ import annotations
import logging
from datetime import datetime, timezone
from pathlib import Path
from mundial_core import cargar_json, guardar_json
log = logging.getLogger(__name__)
CAMPOS_COMPARABLES = [
    "gf_local", "gf_visit",
    "ta_local", "ta_visit",
    "doblea_local", "doblea_visit",
    "rd_local", "rd_visit",
]
CAMPOS_SOLO_ESPN = [
    "penfall_local", "penfall_visit",
    "penpar_local", "penpar_visit",
    "pen_tanda_local", "pen_tanda_visit",
]
def clave(local: str, visit: str) -> str:
    return "|".join(sorted([local, visit]))
def _ahora() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")
def cargar_estado(path: Path) -> dict:
    return cargar_json(path, {})
def guardar_estado(path: Path, estado: dict) -> None:
    guardar_json(path, estado)
def cargar_discrepancias(path: Path) -> list[dict]:
    return cargar_json(path, [])
def guardar_discrepancias(path: Path, discrepancias: list[dict]) -> None:
    guardar_json(path, discrepancias)

def fechas_pendientes(matches: list[dict], estado: dict) -> set:
    """Decide qué fechas hace falta volver a pedirle a ESPN: únicamente
    las de partidos que YA EXISTEN en matches.json (es decir, ya los
    leyó Wikipedia) y que todavía no están marcados como verificados
    en estado_reconciliacion.json (estado.get(clave, {}).get("verificado")).

    Un partido se vuelve a pedir en cada ejecución mientras no esté
    verificado — esto cubre tanto los que aún no tienen ningún dato de
    ESPN como los que ya tienen una discrepancia abierta (así, si la
    fuente se corrige más adelante, la discrepancia se resuelve sola
    en la siguiente conciliación sin intervención manual).

    No se añade ninguna ventana de "últimos N días": si Wikipedia
    todavía no tiene un partido como fila en matches.json, no hay
    fecha que pedir para él aquí (ESPN podría tener el partido antes
    que Wikipedia, pero eso se detectará solo cuando Wikipedia lo
    publique y aparezca la fila — entonces sí entra en este filtro).
    """
    from datetime import date
    fechas = set()
    for m in matches:
        k = clave(m["local"], m["visitante"])
        ya_verificado = estado.get(k, {}).get("verificado", False)
        if ya_verificado:
            continue
        if m.get("fecha"):
            try:
                fechas.add(date.fromisoformat(m["fecha"]))
            except ValueError:
                pass
    return fechas
def _registrar_o_actualizar_discrepancia(
    discrepancias: list[dict], ref: str, match_id, local, visit, campo, valor_wiki, valor_scraper,
) -> list[dict]:
    for d in discrepancias:
        if d["ref"] == ref:
            d["valor_wiki"] = valor_wiki
            d["valor_scraper"] = valor_scraper
            d["detectado"] = _ahora()
            return discrepancias
    discrepancias.append({
        "ref": ref,
        "match_id": match_id,
        "local": local,
        "visitante": visit,
        "campo": campo,
        "valor_wiki": valor_wiki,
        "valor_scraper": valor_scraper,
        "detectado": _ahora(),
    })
    return discrepancias
def _quitar_discrepancia(discrepancias: list[dict], ref: str) -> list[dict]:
    return [d for d in discrepancias if d["ref"] != ref]

def conciliar(
    matches: list[dict],
    resumenes_espn: list[dict],
    estado: dict,
    discrepancias: list[dict],
) -> tuple[list[dict], dict, list[dict], dict]:
    """Devuelve (matches actualizados, estado actualizado, discrepancias
    actualizadas, resumen para el log)."""
    indice_matches = {clave(m["local"], m["visitante"]): m for m in matches}
    resumen = {"verificados_nuevos": 0, "discrepancias_nuevas": 0, "espn_sin_wiki": 0,
               "penaltis_aplicados": 0, "discrepancias_resueltas": 0}

    for r in resumenes_espn:
        if not r.get("completado"):
            continue
        k = clave(r["local"], r["visitante"])
        m = indice_matches.get(k)
        e = estado.setdefault(k, {
            "verificado": False, "ultimo_chequeo": None, "intentos": 0,
            "match_id": None, "valores_espn_aplicados": {},
        })
        e["ultimo_chequeo"] = _ahora()
        e["intentos"] = e.get("intentos", 0) + 1
        discrepancias_antes_de_este_partido = {
            d["ref"] for d in discrepancias if d["ref"].startswith(f"{k}::")
        }
        if m is None:
            # ESPN ya tiene el resultado pero Wikipedia (matches.json)
            # todavía no — no hay nada que fusionar todavía, solo avisar
            # y esperar a la próxima ejecución programada.
            resumen["espn_sin_wiki"] += 1
            ref = f"{k}::partido_no_encontrado_en_wiki"
            if r.get("gf_local") is not None and r.get("gf_visit") is not None:
                discrepancias = _registrar_o_actualizar_discrepancia(
                    discrepancias, ref, None, r["local"], r["visitante"],
                    "partido_no_encontrado_en_wiki",
                    None, f"{r['gf_local']}-{r['gf_visit']}",
                )
            continue
        e["match_id"] = m["id"]
        bloqueados = set(e.get("campos_bloqueados", []))
        hay_discrepancia_pendiente = False
        
        # 1) Campos que existen en las dos fuentes (Se activa si AL MENOS UNO no es nulo)
        if any(m.get(campo) is not None for campo in CAMPOS_COMPARABLES):
            for campo in CAMPOS_COMPARABLES:
                if campo in bloqueados:
                    # El usuario ya decidió este campo a mano una vez:
                    # no se vuelve a comparar ni a pisar nunca más.
                    continue
                ref = f"{k}::{campo}"
                valor_wiki = m.get(campo)
                valor_espn = r.get(campo)
                if valor_espn is None:
                    continue
                if valor_wiki == valor_espn:
                    discrepancias = _quitar_discrepancia(discrepancias, ref)
                else:
                    antes = len(discrepancias)
                    discrepancias = _registrar_o_actualizar_discrepancia(
                        discrepancias, ref, m["id"], m["local"], m["visitante"],
                        campo, valor_wiki, valor_espn,
                    )
                    if len(discrepancias) != antes:
                        resumen["discrepancias_nuevas"] += 1
                    hay_discrepancia_pendiente = True
        else:
            # Wikipedia no tiene absolutamente ningún dato cargado para este partido 
            # (todos los campos comparables están en None)
            hay_discrepancia_pendiente = True

        # 2) Campos que SOLO trae ESPN (penaltis fallados/parados, tanda)
        snapshot = e.get("valores_espn_aplicados", {})
        for campo in CAMPOS_SOLO_ESPN:
            if campo in bloqueados:
                continue
            ref = f"{k}::{campo}"
            valor_actual = m.get(campo)
            valor_espn = r.get(campo)
            if valor_espn is None:
                continue
            valor_previo_aplicado = snapshot.get(campo, 0 if "pen_tanda" not in campo else None)
            tocado_a_mano = valor_actual != valor_previo_aplicado
            if not tocado_a_mano:
                if valor_actual != valor_espn:
                    m[campo] = valor_espn
                    resumen["penaltis_aplicados"] += 1
                snapshot[campo] = valor_espn
                discrepancias = _quitar_discrepancia(discrepancias, ref)
            else:
                if valor_actual == valor_espn:
                    snapshot[campo] = valor_espn
                    discrepancias = _quitar_discrepancia(discrepancias, ref)
                else:
                    antes = len(discrepancias)
                    discrepancias = _registrar_o_actualizar_discrepancia(
                        discrepancias, ref, m["id"], m["local"], m["visitante"],
                        campo, valor_actual, valor_espn,
                    )
                    if len(discrepancias) != antes:
                        resumen["discrepancias_nuevas"] += 1
                    hay_discrepancia_pendiente = True
        e["valores_espn_aplicados"] = snapshot
        # ¿queda alguna discrepancia abierta para este partido?
        discrepancias_despues_de_este_partido = {
            d["ref"] for d in discrepancias if d["ref"].startswith(f"{k}::")
        }
        resueltas_esta_vuelta = discrepancias_antes_de_este_partido - discrepancias_despues_de_este_partido
        if resueltas_esta_vuelta:
            resumen["discrepancias_resueltas"] += len(resueltas_esta_vuelta)
            for ref_resuelta in resueltas_esta_vuelta:
                log.info(f"  RESUELTA  {ref_resuelta} (Wikipedia y ESPN ya coinciden)")
        sigue_con_discrepancias = bool(discrepancias_despues_de_este_partido)
        if not hay_discrepancia_pendiente and not sigue_con_discrepancias:
            if not e["verificado"]:
                resumen["verificados_nuevos"] += 1
            e["verificado"] = True
        else:
            e["verificado"] = False
    return matches, estado, discrepancias, resumen
