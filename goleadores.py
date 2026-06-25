# -*- coding: utf-8 -*-
"""
goleadores.py — Mundial 2026 · Bolilla
=========================================
Wikipedia no trae quién marcó cada gol (al menos no de forma fácil de
parsear de forma fiable), pero ESPN sí. Este módulo guarda, partido a
partido, los goles que ha devuelto espn_scraper.py en
goleadores_por_partido.json (uno por partido, así no hace falta volver
a pedirle a ESPN partidos ya vistos solo para reconstruir la tabla) y
expone una función para calcular la clasificación de máximos
goleadores a partir de ahí.
"""
from __future__ import annotations

from pathlib import Path

from mundial_core import cargar_json, guardar_json


def actualizar_goleadores(resumenes_espn: list[dict], path: Path) -> dict:
    datos = cargar_json(path, {})
    for r in resumenes_espn:
        if not r.get("completado") or not r.get("goleadores"):
            continue
        local, visit, fecha = r["local"], r["visitante"], r.get("fecha") or ""
        clave = f"{'|'.join(sorted([local, visit]))}|{fecha}"
        datos[clave] = r["goleadores"]
    guardar_json(path, datos)
    return datos


def tabla_goleadores(datos: dict) -> list[dict]:
    acumulado = {}
    for goles_partido in datos.values():
        for g in goles_partido:
            jugador, equipo = g.get("jugador") or "Desconocido", g.get("equipo")
            llave = (jugador, equipo)
            acumulado.setdefault(llave, 0)
            acumulado[llave] += 1
    tabla = [
        {"jugador": jugador, "equipo": equipo, "goles": goles}
        for (jugador, equipo), goles in acumulado.items()
    ]
    tabla.sort(key=lambda f: (-f["goles"], f["jugador"]))
    for i, fila in enumerate(tabla, start=1):
        fila["pos"] = i
    return tabla
