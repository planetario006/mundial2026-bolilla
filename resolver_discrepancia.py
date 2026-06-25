# -*- coding: utf-8 -*-
"""
resolver_discrepancia.py — Mundial 2026 · Bolilla
====================================================
Pequeña utilidad de línea de comandos para resolver a mano las
discrepancias que actualizar_mundial.py va dejando en
discrepancias.json cuando Wikipedia y ESPN no coinciden en algo. Aplica
el valor elegido directamente a matches.json y, si era la última
discrepancia pendiente de ese partido, lo marca como "verificado" en
estado_reconciliacion.json (no se volverá a comprobar más).

Uso:
    # Ver todas las discrepancias pendientes, numeradas
    python resolver_discrepancia.py --listar

    # Resolver la discrepancia número 2 usando el valor de Wikipedia
    python resolver_discrepancia.py --indice 2 --usar wiki

    # Resolver usando el valor de ESPN, referenciando por "ref" exacta
    python resolver_discrepancia.py --ref "Argentina|Austria::gf_local" --usar scraper

    # Forzar un valor manual distinto de los dos (por si ninguno acierta)
    python resolver_discrepancia.py --indice 2 --valor 3
"""
from __future__ import annotations

import argparse
from pathlib import Path

import mundial_core as core
import conciliacion as conc

BASE_DIR = Path(__file__).parent
MATCHES_PATH = BASE_DIR / "matches.json"
ESTADO_PATH = BASE_DIR / "estado_reconciliacion.json"
DISCREPANCIAS_PATH = BASE_DIR / "discrepancias.json"
MANUAL_PATH = BASE_DIR / "manual_overrides.json"
GOLEADORES_PATH = BASE_DIR / "goleadores_por_partido.json"
SALIDA_PATH = BASE_DIR / "docs" / "data.json"


def listar(discrepancias: list[dict]) -> None:
    if not discrepancias:
        print("No hay discrepancias pendientes. Todo conciliado. ✔")
        return
    print(f"\n{len(discrepancias)} discrepancia(s) pendiente(s):\n")
    for i, d in enumerate(discrepancias, start=1):
        print(
            f"  [{i}] {d['local']} vs {d['visitante']}  ·  campo: {d['campo']}\n"
            f"        wiki={d['valor_wiki']!r}   scraper={d['valor_scraper']!r}"
            f"   (detectado {d['detectado']})\n"
            f"        ref: {d['ref']}\n"
        )


def resolver(args) -> None:
    matches = core.cargar_json(MATCHES_PATH, [])
    estado = conc.cargar_estado(ESTADO_PATH)
    discrepancias = conc.cargar_discrepancias(DISCREPANCIAS_PATH)

    if args.listar:
        listar(discrepancias)
        return

    if args.indice is not None:
        if not (1 <= args.indice <= len(discrepancias)):
            print(f"Índice fuera de rango. Hay {len(discrepancias)} discrepancia(s); usa --listar.")
            return
        d = discrepancias[args.indice - 1]
    elif args.ref:
        d = next((x for x in discrepancias if x["ref"] == args.ref), None)
        if d is None:
            print(f"No se encontró ninguna discrepancia con ref={args.ref!r}. Usa --listar.")
            return
    else:
        print("Falta --indice o --ref (o usa --listar para ver las pendientes).")
        return

    if d["campo"] == "partido_no_encontrado_en_wiki":
        print(
            f"'{d['local']} vs {d['visitante']}' lo tiene ESPN pero todavía no Wikipedia.\n"
            "No hay nada que aplicar a mano todavía: espera a que Wikipedia publique el "
            "partido (la siguiente ejecución programada lo recogerá sola), o créalo tú "
            "mismo en matches.json si no quieres esperar."
        )
        return

    if args.valor is not None:
        nuevo_valor = args.valor
    elif args.usar == "wiki":
        nuevo_valor = d["valor_wiki"]
    elif args.usar == "scraper":
        nuevo_valor = d["valor_scraper"]
    else:
        print("Indica --usar wiki|scraper, o --valor <numero> para forzar otro valor.")
        return

    match_id = d["match_id"]
    m = next((x for x in matches if x["id"] == match_id), None)
    if m is None:
        print(f"No se encontró el partido id={match_id} en matches.json.")
        return

    valor_anterior = m.get(d["campo"])
    m[d["campo"]] = nuevo_valor
    print(f"{d['local']} vs {d['visitante']} · {d['campo']}: {valor_anterior!r} → {nuevo_valor!r}")

    # Si el campo es uno de los "solo ESPN", actualizamos también el
    # snapshot para que la próxima ejecución no lo vuelva a marcar como
    # discrepancia contra el mismo valor de ESPN.
    k = conc.clave(d["local"], d["visitante"])
    if d["campo"] in conc.CAMPOS_SOLO_ESPN:
        estado.setdefault(k, {}).setdefault("valores_espn_aplicados", {})[d["campo"]] = nuevo_valor

    # Bloqueamos el campo: a partir de ahora se ignora en la
    # conciliación automática, así una ejecución futura de
    # actualizar_mundial.py nunca vuelve a pisar esta decisión, aunque
    # ESPN siga devolviendo el mismo valor que acabas de descartar.
    estado.setdefault(k, {}).setdefault("campos_bloqueados", [])
    if d["campo"] not in estado[k]["campos_bloqueados"]:
        estado[k]["campos_bloqueados"].append(d["campo"])

    discrepancias = conc._quitar_discrepancia(discrepancias, d["ref"])

    quedan = any(x["ref"].startswith(f"{k}::") for x in discrepancias)
    if not quedan and k in estado:
        estado[k]["verificado"] = True
        print(f"  → Sin más discrepancias para este partido: marcado como verificado.")

    core.guardar_json(MATCHES_PATH, matches)
    conc.guardar_estado(ESTADO_PATH, estado)
    conc.guardar_discrepancias(DISCREPANCIAS_PATH, discrepancias)

    # Regenerar data.json automáticamente para que la web refleje el cambio
    # sin necesidad de ejecutar nada más.
    try:
        data = core.construir_y_guardar(MATCHES_PATH, MANUAL_PATH, SALIDA_PATH, GOLEADORES_PATH)
        print(
            f"\n✔ data.json regenerado automáticamente "
            f"({data['meta']['total_partidos_jugados']} partidos jugados)."
        )
    except Exception as e:
        print(
            f"\n⚠ No se pudo regenerar data.json automáticamente: {e}\n"
            f"  Ejecuta mundial_core.py manualmente para actualizar la web."
        )


def main():
    parser = argparse.ArgumentParser(description="Resolver discrepancias Wikipedia vs ESPN")
    parser.add_argument("--listar", action="store_true", help="Lista las discrepancias pendientes")
    parser.add_argument("--indice", type=int, default=None, help="Número de la discrepancia (ver --listar)")
    parser.add_argument("--ref", default=None, help="Referencia exacta de la discrepancia")
    parser.add_argument("--usar", choices=["wiki", "scraper"], default=None,
                         help="Qué fuente usar para resolver el valor")
    parser.add_argument("--valor", type=int, default=None,
                         help="Forzar un valor numérico manual distinto de los dos")
    args = parser.parse_args()
    resolver(args)


if __name__ == "__main__":
    main()
