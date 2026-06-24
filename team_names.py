# team_names.py
# -*- coding: utf-8 -*-
"""Diccionario único de nombres de selección, compartido entre la fuente
Wikipedia y la fuente ESPN. Si en el futuro ESPN devuelve un nombre que no
está aquí, añádelo en este archivo — es el único sitio donde hace falta."""

NOMBRE_MAP = {
    # ... pega aquí EXACTAMENTE el diccionario NOMBRE_MAP que ya tienes
    # en actualizar_mundial.py (líneas 105-147 del archivo actual)
}

def traducir(nombre: str) -> str:
    n = nombre.strip()
    return NOMBRE_MAP.get(n, n)
