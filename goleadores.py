# -*- coding: utf-8 -*-
"""
goleadores.py — Mundial 2026 · Bolilla
=========================================
Wikipedia no trae quién marcó cada gol ni quién asistió (al menos no
de forma fácil de parsear de forma fiable), pero ESPN sí. Este módulo
mantiene en goleadores_totales.json el acumulado de goles y
asistencias por jugador — no el detalle partido a partido, porque lo
único que hace falta para la tabla de máximo goleador es el total y
el desempate por asistencias.

Para no contar dos veces un mismo partido si se reprocesa (por
ejemplo si conciliacion.py lo vuelve a pasar por cualquier motivo),
se guarda también un set con las claves de los partidos ya aplicados
al acumulado ("_procesados"). Ese set es solo una guarda interna, no
un histórico consultable — si se necesitara reconstruir la tabla
desde cero habría que volver a pedirle a ESPN los partidos.

Esquema de goleadores_totales.json:
{
  "_procesados": ["México|Sudáfrica|2026-06-11", ...],
  "jugadores": {
    "Julián Quiñones|México": {
      "jugador": "Julián Quiñones", "equipo": "México",
      "goles": 2, "asistencias": 0
    },
    ...
  }
}
"""
from __future__ import annotations

from pathlib import Path

from mundial_core import cargar_json, guardar_json

_VACIO = {"_procesados": [], "jugadores": {}}


def actualizar_goleadores(resumenes_espn: list[dict], path: Path) -> dict:
    datos = cargar_json(path, _VACIO)
    procesados = set(datos.get("_procesados", []))
    jugadores = datos.get("jugadores", {})

    for r in resumenes_espn:
        if not r.get("completado") or not r.get("goleadores"):
            continue
        local, visit, fecha = r["local"], r["visitante"], r.get("fecha") or ""
        clave_partido = f"{'|'.join(sorted([local, visit]))}|{fecha}"
        if clave_partido in procesados:
            continue  # ya aplicado a los totales, evita doble conteo

        for g in r["goleadores"]:
            jugador, equipo = g.get("jugador") or "Desconocido", g.get("equipo")
            llave = f"{jugador}|{equipo}"
            fila = jugadores.setdefault(
                llave, {"jugador": jugador, "equipo": equipo, "goles": 0, "asistencias": 0}
            )
            fila["goles"] += 1

            asistente = g.get("asistente")
            if asistente:
                llave_asist = f"{asistente}|{equipo}"
                fila_asist = jugadores.setdefault(
                    llave_asist,
                    {"jugador": asistente, "equipo": equipo, "goles": 0, "asistencias": 0},
                )
                fila_asist["asistencias"] += 1

        procesados.add(clave_partido)

    datos = {"_procesados": sorted(procesados), "jugadores": jugadores}
    guardar_json(path, datos)
    return datos


def tabla_goleadores(datos: dict) -> list[dict]:
    jugadores = datos.get("jugadores", {})
    tabla = [dict(fila) for fila in jugadores.values()]
    # Desempate: más goles primero, luego más asistencias, luego alfabético
    tabla.sort(key=lambda f: (-f["goles"], -f["asistencias"], f["jugador"]))
    for i, fila in enumerate(tabla, start=1):
        fila["pos"] = i
    return tabla
