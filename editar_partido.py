# -*- coding: utf-8 -*-
"""
editar_partido.py — Mundial 2026 · Bolilla (Versión Final)
"""
from __future__ import annotations

import sys
import argparse
from pathlib import Path

import mundial_core as core
import conciliacion as conc

BASE_DIR = Path(__file__).parent
MATCHES_PATH = BASE_DIR / "matches.json"
ESTADO_PATH = BASE_DIR / "estado_reconciliacion.json"
MANUAL_PATH = BASE_DIR / "manual_overrides.json"
GOLEADORES_PATH = BASE_DIR / "goleadores_por_partido.json"
SALIDA_PATH = BASE_DIR / "docs" / "data.json"

def limpiar_pantalla():
    print("\n" * 2)

def seleccionar_opcion(opciones, mensaje="Elige una opción: "):
    for i, opc in enumerate(opciones, 1):
        print(f"  [{i}] {opc}")
    while True:
        try:
            sel = int(input(f"\n{mensaje}"))
            if 1 <= sel <= len(opciones):
                return sel - 1
            print("❌ Opción no válida.")
        except ValueError:
            print("❌ Por favor, introduce un número.")

def aplicar_cambio(m, campo, valor, matches, estado):
    valor_anterior = m.get(campo, 0)
    m[campo] = valor
    print(f"\n✔ ¡Hecho! '{campo}' cambiado en ID {m['id']}: {valor_anterior} → {valor}")
    k = conc.clave(m["local"], m["visitante"])
    estado.setdefault(k, {}).setdefault("campos_bloqueados", [])
    if campo not in estado[k]["campos_bloqueados"]:
        estado[k]["campos_bloqueados"].append(campo)
    core.guardar_json(MATCHES_PATH, matches)
    conc.guardar_estado(ESTADO_PATH, estado)
    try:
        core.construir_y_guardar(MATCHES_PATH, MANUAL_PATH, SALIDA_PATH, GOLEADORES_PATH)
        print("🌐 data.json regenerado.")
    except Exception as e:
        print(f"⚠ Error regenerando data.json: {e}")

def asignar_jornadas_local(matches):
    """Lógica interna: calcula jornadas solo para esta sesión de edición"""
    grupos = {}
    for m in matches:
        if m.get("fase") == "Fase de Grupos":
            grupo = m["grupo"]
            if grupo not in grupos: grupos[grupo] = []
            grupos[grupo].append(m)
    for g in grupos:
        partidos = sorted(grupos[g], key=lambda x: x['fecha'])
        for i, p in enumerate(partidos):
            p['jornada'] = (i // 2) + 1
    return matches

def modo_interactivo(matches, estado):
    limpiar_pantalla()
    matches = asignar_jornadas_local(matches)
    print("⚽ EDITOR INTERACTIVO · MUNDIAL 2026")
    opciones_filtro = ["Fase de Grupos", "Fases Eliminatorias", "Salir"]
    sel_filtro = seleccionar_opcion(opciones_filtro)
    if sel_filtro == 2: sys.exit(0)
    partidos_filtrados = []
    
    if sel_filtro == 0: # Grupos
        sub_opciones = ["Filtrar por Grupo", "Filtrar por Jornada"]
        sel_sub = seleccionar_opcion(sub_opciones)
        if sel_sub == 0:
            grupos = sorted(list(set(m["grupo"] for m in matches if m.get("grupo"))))
            sel_g = seleccionar_opcion(grupos)
            partidos_filtrados = [m for m in matches if m.get("grupo") == grupos[sel_g]]
        else:
            sel_j = seleccionar_opcion(["Jornada 1", "Jornada 2", "Jornada 3"])
            partidos_filtrados = [m for m in matches if m.get("jornada") == sel_j + 1]
    else: # Eliminatorias
        fases = ["Dieciseisavos de final", "Octavos de final", "Cuartos de final", "Semifinales", "Tercer puesto", "Final"]
        sel_f = seleccionar_opcion(fases)
        partidos_filtrados = [m for m in matches if m.get("fase") == fases[sel_f]]

    if not partidos_filtrados:
        print("\n❌ No hay partidos registrados con ese criterio.")
        return

    print("\nPartidos encontrados:")
    opciones_partidos = []
    for m in partidos_filtrados:
        marcador = f"{m.get('gf_local', '-')} - {m.get('gf_visit', '-')}"
        opciones_partidos.append(f"{m['local']:>15}  {marcador:^7}  {m['visitante']:<15} (ID: {m['id']})")
    
    opciones_partidos.append("<- Cancelar")
    sel_partido = seleccionar_opcion(opciones_partidos, "Elige el partido a editar: ")
    
    if sel_partido == len(opciones_partidos) - 1:
        return

    m_elegido = partidos_filtrados[sel_partido]
    m = next((x for x in matches if x["id"] == m_elegido["id"]), None)

    limpiar_pantalla()
    print(f"🏟️ EDITANDO: {m['local']} vs {m['visitante']}")
    
    campos_editables = [
        ("Goles Local", "gf_local"), ("Goles Visitante", "gf_visit"),
        ("T. Amarillas Local", "ta_local"), ("T. Amarillas Visitante", "ta_visit"),
        ("Doble Amarilla Local", "doblea_local"), ("Doble Amarilla Visitante", "doblea_visit"),
        ("Roja Directa Local", "rd_local"), ("Roja Directa Visitante", "rd_visit"),
        ("Penaltis Fallados Local", "penfall_local"), ("Penaltis Fallados Visitante", "penfall_visit"),
        ("Penaltis Parados Local", "penpar_local"), ("Penaltis Parados Visitante", "penpar_visit"),
    ]

    opciones_campos = [f"{lbl} (Actual: {m.get(key, 0)})" for lbl, key in campos_editables]
    opciones_campos.append("<- Cancelar")
    sel_campo_idx = seleccionar_opcion(opciones_campos, "¿Qué estadística quieres modificar? ")
    
    if sel_campo_idx == len(opciones_campos) - 1:
        return
        
    _, clave_campo = campos_editables[sel_campo_idx]
    
    while True:
        nuevo_val_str = input("\nIntroduce el NUEVO VALOR (entero): ")
        if not nuevo_val_str.strip(): return
        try:
            nuevo_valor = int(nuevo_val_str)
            break
        except ValueError:
            print("❌ Número no válido.")

    aplicar_cambio(m, clave_campo, nuevo_valor, matches, estado)

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--id", type=int, help="ID del partido a editar")
    parser.add_argument("--campo", type=str, help="Campo a modificar")
    parser.add_argument("--valor", type=str, help="Nuevo valor")
    args = parser.parse_args()

    matches = core.cargar_json(MATCHES_PATH, [])
    estado = conc.cargar_estado(ESTADO_PATH)

    # Si nos pasan argumentos desde GitHub Actions, usamos el modo directo
    if args.id is not None and args.campo is not None and args.valor is not None:
        m = next((x for x in matches if x["id"] == args.id), None)
        if not m:
            print(f"Error: Partido con ID {args.id} no encontrado.")
            sys.exit(1)
            
        nuevo_valor = int(args.valor) if args.valor.lstrip('-').isdigit() else args.valor
        aplicar_cambio(m, args.campo, nuevo_valor, matches, estado)
    
    # Si no nos pasan argumentos (VS Code), abrimos el menú interactivo
    else:
        try:
            modo_interactivo(matches, estado)
        except KeyboardInterrupt:
            print("\nSaliendo...")
            sys.exit(0)

if __name__ == "__main__":
    main()
