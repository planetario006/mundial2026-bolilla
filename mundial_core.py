# -*- coding: utf-8 -*-
"""
mundial_core.py — Mundial 2026 · Bolilla
=========================================
Motor de cálculo en Python puro. Es la réplica exacta de la lógica que antes
vivía en las macros VBA del .xlsm (ClasificacionMundial2026.bas y
Módulo1.bas), para que pueda ejecutarse en cualquier sitio (incluida una
máquina en la nube sin Windows ni Excel instalado).
No depende de Excel para nada: lee partidos desde matches.json, aplica las
reglas de puntuación y desempate FIFA, y escribe data.json (la "foto" que
luego consume el dashboard móvil).
Estructura de datos de un partido (matches.json), igual que las columnas
de la hoja "Partidos" del Excel original:
{
  "id": 1, "fecha": "2026-06-11", "fase": "Fase de Grupos", "grupo": "A",
  "local": "México", "gf_local": 2, "gc_local": 0, "ta_local": 1,
  "doblea_local": 0, "rd_local": 1, "penfall_local": 0, "penpar_local": 0,
  "visitante": "Sudáfrica", "gf_visit": 0, "gc_visit": 2, "ta_visit": 2,
  "doblea_visit": 0, "rd_visit": 2, "penfall_visit": 0, "penpar_visit": 0,
  "pen_tanda_local": null, "pen_tanda_visit": null
}
Los campos penfall_*/penpar_* (penaltis fallados/parados) son SIEMPRE
manuales: el actualizador automático los crea a 0 y nunca vuelve a
tocarlos. Si alguien quiere anotar un penalti parado, se edita ese número
directamente en matches.json (por ejemplo desde el editor web de GitHub,
también funciona desde el móvil) y el resto del sistema lo recoge solo en
la siguiente ejecución.
"""
from __future__ import annotations
import json
from pathlib import Path
from datetime import datetime, timezone
# ─────────────────────────────────────────────────────────────────────────
# ESTRUCTURA FIJA DEL TORNEO (Mundial 2026 · 48 equipos · 12 grupos de 4)
# ─────────────────────────────────────────────────────────────────────────
GRUPOS = {
    "A": ["México", "Sudáfrica", "Corea del Sur", "Chequia"],
    "B": ["Canadá", "Catar", "Bosnia", "Suiza"],
    "C": ["Brasil", "Marruecos", "Haití", "Escocia"],
    "D": ["EE.UU.", "Paraguay", "Australia", "Turquía"],
    "E": ["Alemania", "Curazao", "Costa de Marfil", "Ecuador"],
    "F": ["Países Bajos", "Japón", "Suecia", "Túnez"],
    "G": ["Bélgica", "Egipto", "Irán", "Nueva Zelanda"],
    "H": ["España", "Cabo Verde", "Arabia Saudí", "Uruguay"],
    "I": ["Francia", "Senegal", "Irak", "Noruega"],
    "J": ["Argentina", "Argelia", "Austria", "Jordania"],
    "K": ["Portugal", "R. D. Congo", "Uzbekistán", "Colombia"],
    "L": ["Inglaterra", "Croacia", "Ghana", "Panamá"],
}
BOMBOS = {
    "Bombo 1": ["España", "Alemania", "Brasil", "Francia", "Inglaterra", "Argentina"],
    "Bombo 2": ["Portugal", "México", "Marruecos", "Países Bajos", "Croacia", "Bélgica"],
    "Bombo 3": ["Colombia", "Suecia", "Noruega", "Uruguay", "Canadá", "Senegal"],
    "Bombo 4": ["Chequia", "Japón", "EE.UU.", "Túnez", "Ecuador", "Suiza"],
    "Bombo 5": ["Arabia Saudí", "Turquía", "Escocia", "Corea del Sur", "Bosnia", "Paraguay"],
    "Bombo 6": ["Austria", "Sudáfrica", "Australia", "Costa de Marfil", "Egipto", "Nueva Zelanda"],
    "Bombo 7": ["Argelia", "R. D. Congo", "Catar", "Irak", "Panamá", "Uzbekistán"],
    "Bombo 8": ["Haití", "Irán", "Jordania", "Ghana", "Curazao", "Cabo Verde"],
}
EQUIPO_A_GRUPO = {eq: g for g, eqs in GRUPOS.items() for eq in eqs}
EQUIPO_A_BOMBO = {eq: b for b, eqs in BOMBOS.items() for eq in eqs}
TODOS_LOS_EQUIPOS = sorted(EQUIPO_A_GRUPO.keys())
# Orden e identificación de las fases eliminatorias (debe coincidir con el
# texto exacto que se guarda en el campo "fase" de cada partido)
FASES_ELIMINACION = [
    "Dieciseisavos de final",
    "Octavos de final",
    "Cuartos de final",
    "Semifinales",
    "Tercer puesto",
    "Final",
]
# Clave corta por fase eliminatoria — se usa para exponer el bonus de cada
# ronda por separado (en vez de un único "bonus_ronda" agregado) tanto en
# data.json como en el desglose de la app.
FASES_KEYS = {
    "Dieciseisavos de final": "dieciseisavos",
    "Octavos de final": "octavos",
    "Cuartos de final": "cuartos",
    "Semifinales": "semifinal",
    "Final": "final",
}
FASE_GRUPOS_TXT = "Fase de Grupos"
# Cuántos de los 12 terceros de grupo pasan a dieciseisavos (formato de
# 48 equipos / 12 grupos de 4: los 2 primeros de cada grupo + los 8
# mejores terceros).
N_TERCEROS_CLASIFICAN = 8
# ─────────────────────────────────────────────────────────────────────────
# SISTEMA DE PUNTUACIÓN OFICIAL (hoja "Sistema Puntuación")
# ─────────────────────────────────────────────────────────────────────────
PUNTOS_GOL_FAVOR = 1
PUNTOS_GOL_CONTRA = -3
PUNTOS_TARJETA_AMARILLA = -3
PUNTOS_DOBLE_AMARILLA = -7
PUNTOS_ROJA_DIRECTA = -12
PUNTOS_PENALTI_FALLADO = -10
PUNTOS_PENALTI_PARADO = 5
PUNTOS_PARTIDO_GANADO = 5
PUNTOS_PARTIDO_EMPATADO = 2
PUNTOS_PARTIDO_PERDIDO = -8
PUNTOS_POS_GRUPO = {1: 15, 2: 10, 3: 5, 4: 0}
PUNTOS_BONUS_RONDA = {
    "Dieciseisavos de final": 25,
    "Octavos de final": 35,
    "Cuartos de final": 50,
    "Semifinales": 70,
    "Final": 100,
}
PUNTOS_PREMIO_FINAL = {
    "campeon": 170,
    "subcampeon": 130,
    "tercero": 100,
    "cuarto": 60,
}
PUNTOS_MAXIMO_GOLEADOR = 25

# ─────────────────────────────────────────────────────────────────────────
# AGREGADOS POR EQUIPO A PARTIR DE LOS PARTIDOS
# ─────────────────────────────────────────────────────────────────────────
def _nuevo_marcador():
    return {
        "PJ": 0, "PG": 0, "PE": 0, "PP": 0,
        "GF": 0, "GC": 0, "TA": 0, "DA": 0, "RD": 0,
        "PenFall": 0, "PenPar": 0,
        "Pts": 0, "DG": 0, "FairPlay": 0,
        "PtsResultado": 0,
    }
def jugado(p: dict) -> bool:
    """Un partido cuenta como jugado si tiene goles registrados en ambos lados."""
    return p.get("gf_local") is not None and p.get("gf_visit") is not None
def resultado_local(p: dict) -> str:
    """'V' / 'E' / 'L' desde el punto de vista del equipo local."""
    if p["gf_local"] > p["gf_visit"]:
        return "V"
    if p["gf_local"] < p["gf_visit"]:
        return "L"
    return "E"
def calcular_stats_globales(matches: list[dict]) -> dict:
    """Estadísticas acumuladas de TODOS los partidos de la lista recibida,
    una entrada por cada uno de los 48 equipos.
    Importante: esta función es agnóstica de fase — agrega lo que se le
    pase. Quien la llama decide si le pasa todos los partidos del torneo
    (para el desglose total de puntos de la bolilla) o solo los de fase
    de grupos (para clasificar grupos y para elegir a los mejores
    terceros), ver `calcular_puntos_totales`."""
    stats = {eq: _nuevo_marcador() for eq in TODOS_LOS_EQUIPOS}
    for p in matches:
        if not jugado(p):
            continue
        res = resultado_local(p)
        pts_local = {"V": PUNTOS_PARTIDO_GANADO, "E": PUNTOS_PARTIDO_EMPATADO, "L": PUNTOS_PARTIDO_PERDIDO}[res]
        pts_visit = {"V": PUNTOS_PARTIDO_PERDIDO, "E": PUNTOS_PARTIDO_EMPATADO, "L": PUNTOS_PARTIDO_GANADO}[res]
        for lado, equipo, gf, gc, ta, da, rd, pf, pp, ptsres in (
            ("local", p["local"], p["gf_local"], p["gc_local"], p["ta_local"],
             p["doblea_local"], p["rd_local"], p["penfall_local"], p["penpar_local"], pts_local),
            ("visit", p["visitante"], p["gf_visit"], p["gc_visit"], p["ta_visit"],
             p["doblea_visit"], p["rd_visit"], p["penfall_visit"], p["penpar_visit"], pts_visit),
        ):
            if equipo not in stats:
                stats[equipo] = _nuevo_marcador()
            s = stats[equipo]
            s["PJ"] += 1
            if gf > gc:
                s["PG"] += 1
            elif gf == gc:
                s["PE"] += 1
            else:
                s["PP"] += 1
            s["GF"] += gf
            s["GC"] += gc
            s["TA"] += ta
            s["DA"] += da
            s["RD"] += rd
            s["PenFall"] += pf
            s["PenPar"] += pp
            s["PtsResultado"] += ptsres
    for s in stats.values():
        s["Pts"] = s["PG"] * 3 + s["PE"] * 1
        s["DG"] = s["GF"] - s["GC"]
        s["FairPlay"] = -(s["TA"] * 1 + s["DA"] * 3 + s["RD"] * 4)

    return stats
# ─────────────────────────────────────────────────────────────────────────
# CLASIFICACIÓN DE GRUPO — CRITERIOS OFICIALES FIFA (réplica de la VBA)
#   1-3. Enfrentamientos directos (puntos, DG, GF), reaplicados de forma
#        recursiva al subconjunto que siga empatado.
#   4-5. Diferencia de goles / goles a favor en TODOS los partidos del grupo.
#   6.   Fair Play (amarilla -1 / doble amarilla -3 / roja directa -4).
#   7.   Ranking FIFA — no disponible automáticamente; si llega aquí el
#        empate queda señalado para resolver a mano.
#
# IMPORTANTE: el parámetro `stats` que recibe `clasificar_grupo` debe venir
# calculado SOLO con partidos de fase de grupos (`stats_grupos` en
# `calcular_puntos_totales`), nunca con las estadísticas de todo el
# torneo — si no, en cuanto empezara la eliminatoria, los goles/tarjetas
# de octavos, cuartos, etc. se colarían en el desempate de un grupo que ya
# terminó hace semanas.
# ─────────────────────────────────────────────────────────────────────────
def _mini_stats(equipos: list[str], partidos_grupo: list[dict]) -> dict:
    """Mini-tabla calculada SOLO con los enfrentamientos directos entre 'equipos'."""
    mini = {eq: {"Pts": 0, "DG": 0, "GF": 0} for eq in equipos}
    eq_set = set(equipos)
    for p in partidos_grupo:
        if p["local"] in eq_set and p["visitante"] in eq_set:
            gfl, gfv = p["gf_local"], p["gf_visit"]
            mini[p["local"]]["GF"] += gfl
            mini[p["local"]]["DG"] += gfl - gfv
            mini[p["visitante"]]["GF"] += gfv
            mini[p["visitante"]]["DG"] += gfv - gfl
            if gfl > gfv:
                mini[p["local"]]["Pts"] += 3
            elif gfl == gfv:
                mini[p["local"]]["Pts"] += 1
                mini[p["visitante"]]["Pts"] += 1
            else:
                mini[p["visitante"]]["Pts"] += 3
    return mini
def _resolver_empate_h2h(equipos: list[str], partidos_grupo: list[dict]) -> list[list[str]]:
    """Devuelve una lista de "clusters": cada cluster de tamaño 1 está resuelto;
    uno de tamaño >1 sigue empatado tras agotar enfrentamiento directo."""
    if len(equipos) <= 1:
        return [list(equipos)]
    mini = _mini_stats(equipos, partidos_grupo)
    orden = sorted(equipos, key=lambda eq: (mini[eq]["Pts"], mini[eq]["DG"], mini[eq]["GF"]), reverse=True)
    resultado = []
    i = 0
    while i < len(orden):
        terna = (mini[orden[i]]["Pts"], mini[orden[i]]["DG"], mini[orden[i]]["GF"])
        j = i + 1
        while j < len(orden) and (mini[orden[j]]["Pts"], mini[orden[j]]["DG"], mini[orden[j]]["GF"]) == terna:
            j += 1
        bloque = orden[i:j]
        if len(bloque) == len(equipos) or len(bloque) == 1:
            # El enfrentamiento directo no separó a nadie (o ya está resuelto)
            resultado.append(bloque)
        else:
            # Progreso parcial: reaplicar SOLO a este subconjunto
            resultado.extend(_resolver_empate_h2h(bloque, partidos_grupo))
        i = j
    return resultado
def _criterios_globales(equipos: list[str], stats: dict) -> list[tuple[str, bool]]:
    """Criterios 4-6: DG global, GF global, Fair Play (criterio 7, ranking FIFA, se omite).
    Devuelve pares (equipo, sigue_empatado): 'sigue_empatado' solo es True si,
    incluso tras estos tres criterios, dos o más equipos siguen teniendo
    exactamente la misma terna (DG, GF, FairPlay) — ahí ya no hay forma
    automática de deshacer el empate y hace falta el Ranking FIFA o resolverlo
    a mano."""
    orden = sorted(
        equipos,
        key=lambda eq: (stats[eq]["DG"], stats[eq]["GF"], stats[eq]["FairPlay"]),
        reverse=True,
    )
    ternas = [(stats[eq]["DG"], stats[eq]["GF"], stats[eq]["FairPlay"]) for eq in orden]
    return [
        (eq, ternas.count(terna) > 1)
        for eq, terna in zip(orden, ternas)
    ]
def clasificar_grupo(letra: str, matches: list[dict], stats: dict) -> list[dict]:
    """Devuelve la tabla del grupo `letra` ordenada con criterios FIFA,
    incluyendo PJ/PG/PE/PP/GF/GC/DG/Pts y 'empate_sin_resolver' si procede.
    `stats` debe venir calculado SOLO con partidos de fase de grupos."""
    equipos = GRUPOS[letra]
    partidos_grupo = [
        p for p in matches
        if jugado(p) and p.get("grupo") == letra and p.get("fase") == FASE_GRUPOS_TXT
    ]
    orden_inicial = sorted(equipos, key=lambda eq: stats[eq]["Pts"], reverse=True)
    tabla_final = []
    i = 0
    while i < len(orden_inicial):
        pts = stats[orden_inicial[i]]["Pts"]
        j = i + 1
        while j < len(orden_inicial) and stats[orden_inicial[j]]["Pts"] == pts:
            j += 1
        bloque = orden_inicial[i:j]
        if len(bloque) == 1:
            tabla_final.append((bloque[0], False))
        else:
            clusters = _resolver_empate_h2h(bloque, partidos_grupo)
            for cluster in clusters:
                if len(cluster) == 1:
                    tabla_final.append((cluster[0], False))
                else:
                    tabla_final.extend(_criterios_globales(cluster, stats))
        i = j
    resultado = []
    for pos, (eq, posible_empate) in enumerate(tabla_final, start=1):
        s = stats[eq]
        resultado.append({
            "pos": pos,
            "equipo": eq,
            "pj": s["PJ"], "pg": s["PG"], "pe": s["PE"], "pp": s["PP"],
            "gf": s["GF"], "gc": s["GC"], "dg": s["DG"], "pts": s["Pts"],
            "empate_no_resuelto": posible_empate,
        })
    return resultado

# ─────────────────────────────────────────────────────────────────────────
# FASE DE GRUPOS: ¿YA HA TERMINADO?
#   matches.json solo contiene partidos que YA se jugaron (el actualizador
#   nunca precarga partidos futuros con marcador nulo), así que para saber
#   si la fase de grupos ha terminado comparamos cuántos partidos de fase
#   de grupos hay jugados contra cuántos se esperan en total (round-robin
#   completo en los 12 grupos).
# ─────────────────────────────────────────────────────────────────────────
def _partidos_esperados_grupo(n_equipos: int) -> int:
    return n_equipos * (n_equipos - 1) // 2
def fase_grupos_terminada(matches: list[dict]) -> bool:
    esperados = sum(_partidos_esperados_grupo(len(eqs)) for eqs in GRUPOS.values())
    jugados = sum(
        1 for p in matches
        if p.get("fase") == FASE_GRUPOS_TXT and jugado(p)
    )
    return jugados >= esperados

# ─────────────────────────────────────────────────────────────────────────
# MEJORES TERCEROS — quiénes de los 12 terceros de grupo pasan a
# dieciseisavos (los 8 mejores). Mismos criterios que dentro de un grupo
# cuando se agota el enfrentamiento directo (no aplica aquí, son equipos de
# grupos distintos): Pts, DG, GF, Fair Play — y si DOS O MÁS equipos siguen
# empatados en eso justo en la frontera de los 8 (es decir, el empate
# afecta a quién pasa o no), se desempata por Ranking FIFA
# (manual_overrides.json -> "ranking_fifa": {"España": 1, ...}, más bajo
# es mejor). Si ese dato falta o también está repetido, el bloque entero
# se marca "empate_no_resuelto" y, por prudencia, ninguno de esos equipos
# cobra los 5 puntos de tercero hasta que se resuelva a mano.
# Los empates que NO afectan a la frontera (p.ej. dos equipos empatados
# pero ambos claramente dentro o ambos claramente fuera de los 8) no
# necesitan desempate: todos los del bloque comparten el mismo resultado
# de clasificación.
# ─────────────────────────────────────────────────────────────────────────
def _fila_tercero(eq: str, stats: dict, ranking_fifa: dict, clasifica: bool, empate: bool) -> dict:
    s = stats[eq]
    return {
        "equipo": eq,
        "grupo": EQUIPO_A_GRUPO[eq],
        "pts": s["Pts"], "dg": s["DG"], "gf": s["GF"], "fairplay": s["FairPlay"],
        "ranking_fifa": ranking_fifa.get(eq),
        "clasifica": clasifica,
        "empate_no_resuelto": empate,
    }
def calcular_mejores_terceros(clasificaciones: dict, stats: dict, ranking_fifa: dict) -> tuple[set[str], list[dict]]:
    """`stats` debe venir calculado SOLO con partidos de fase de grupos.
    Devuelve (conjunto de equipos que clasifican, tabla ordenada de los 12
    terceros con el detalle de cada uno)."""
    terceros = []
    for tabla in clasificaciones.values():
        fila3 = next((f for f in tabla if f["pos"] == 3), None)
        if fila3:
            terceros.append(fila3["equipo"])

    def terna(eq):
        s = stats[eq]
        return (s["Pts"], s["DG"], s["GF"], s["FairPlay"])

    orden = sorted(terceros, key=terna, reverse=True)

    # Agrupar en bloques empatados en la terna (Pts, DG, GF, FairPlay)
    bloques = []
    i = 0
    while i < len(orden):
        t = terna(orden[i])
        j = i + 1
        while j < len(orden) and terna(orden[j]) == t:
            j += 1
        bloques.append(orden[i:j])
        i = j

    tabla = []
    ocupadas = 0                       # plazas ya asignadas como "clasifica"
    frontera_sin_resolver = False      # un bloque anterior cruzó la frontera y no se pudo desempatar
    for bloque in bloques:
        if frontera_sin_resolver:
            # Cualquier equipo peor que un bloque ya irresoluble queda
            # fuera con seguridad (es estrictamente peor en Pts/DG/GF/FP).
            for eq in bloque:
                tabla.append(_fila_tercero(eq, stats, ranking_fifa, False, True))
            continue

        inicio, fin = ocupadas + 1, ocupadas + len(bloque)

        if fin <= N_TERCEROS_CLASIFICAN:
            # Todo el bloque clasifica — el empate (si lo hay) es cosmético,
            # no afecta a quién pasa.
            for eq in bloque:
                tabla.append(_fila_tercero(eq, stats, ranking_fifa, True, len(bloque) > 1))
            ocupadas = fin

        elif inicio > N_TERCEROS_CLASIFICAN:
            # Todo el bloque queda fuera, tampoco hace falta desempatar.
            for eq in bloque:
                tabla.append(_fila_tercero(eq, stats, ranking_fifa, False, len(bloque) > 1))

        else:
            # El bloque cruza la frontera de los 8: aquí el empate SÍ
            # decide quién pasa. Intentamos resolverlo con Ranking FIFA.
            huecos_libres = N_TERCEROS_CLASIFICAN - ocupadas
            con_fifa = {eq: ranking_fifa[eq] for eq in bloque if eq in ranking_fifa}
            resoluble = (
                len(con_fifa) == len(bloque)
                and len(set(con_fifa.values())) == len(bloque)
            )
            if resoluble:
                orden_bloque = sorted(bloque, key=lambda eq: con_fifa[eq])  # menor = mejor
                for k, eq in enumerate(orden_bloque):
                    tabla.append(_fila_tercero(eq, stats, ranking_fifa, k < huecos_libres, False))
                ocupadas = N_TERCEROS_CLASIFICAN
            else:
                # Falta el dato de Ranking FIFA de alguno, o hay un empate
                # también ahí: no hay forma automática de decidir. Nadie
                # del bloque cobra los puntos hasta que se rellene/corrija
                # "ranking_fifa" en manual_overrides.json.
                for eq in bloque:
                    tabla.append(_fila_tercero(eq, stats, ranking_fifa, False, True))
                frontera_sin_resolver = True

    pasan = {f["equipo"] for f in tabla if f["clasifica"]}
    return pasan, tabla

# ─────────────────────────────────────────────────────────────────────────
# BONUS POR POSICIÓN DE GRUPO Y POR RONDA ELIMINATORIA
# ─────────────────────────────────────────────────────────────────────────
def equipos_que_jugaron_fase(matches: list[dict], fase: str) -> set[str]:
    s = set()
    for p in matches:
        if jugado(p) and p.get("fase") == fase:
            s.add(p["local"])
            s.add(p["visitante"])
    return s
def calcular_bonus_ronda(matches: list[dict]) -> dict:
    """Devuelve, por equipo, un dict {clave_fase: puntos} — el bonus de
    CADA ronda eliminatoria por separado, en vez de un único total
    agregado, para que el desglose de la app pueda mostrar una fila por
    ronda (Dieciseisavos, Octavos, Cuartos, Semifinal, Final)."""
    bonus = {eq: {fk: 0 for fk in FASES_KEYS.values()} for eq in TODOS_LOS_EQUIPOS}
    for fase, puntos in PUNTOS_BONUS_RONDA.items():
        fase_key = FASES_KEYS[fase]
        for eq in equipos_que_jugaron_fase(matches, fase):
            if eq not in bonus:
                bonus[eq] = {fk: 0 for fk in FASES_KEYS.values()}
            bonus[eq][fase_key] = puntos
    return bonus
def calcular_bonus_grupo(matches: list[dict], clasificaciones: dict, mejores_terceros: set[str]) -> dict:
    """Puntos por posición de grupo (1º/2º/3º/4º).
    Mientras la fase de grupos no ha terminado, NADIE cobra todavía estos
    puntos (las cuatro posiciones están a 0) — la clasificación de un
    grupo a mitad de fase es provisional y no debe puntuar.
    Una vez termina, 1º/2º/4º puntúan como siempre, y el 3º solo puntúa
    si ese equipo está entre los 8 mejores terceros que pasan a
    dieciseisavos (los otros 4 terceros se quedan en 0)."""
    bonus = {}
    if not fase_grupos_terminada(matches):
        for tabla in clasificaciones.values():
            for fila in tabla:
                bonus[fila["equipo"]] = 0
        return bonus
    for tabla in clasificaciones.values():
        for fila in tabla:
            pos, eq = fila["pos"], fila["equipo"]
            if pos == 3:
                bonus[eq] = PUNTOS_POS_GRUPO[3] if eq in mejores_terceros else 0
            else:
                bonus[eq] = PUNTOS_POS_GRUPO.get(pos, 0)
    return bonus
def calcular_puntos_totales(matches: list[dict], manual: dict):
    """Devuelve (puntos_por_equipo, clasificaciones, tabla_mejores_terceros)."""
    # Estadísticas de TODO el torneo — para el desglose total de puntos de
    # la bolilla (goles, tarjetas, resultados... de cualquier fase).
    stats = calcular_stats_globales(matches)
    # Estadísticas SOLO de fase de grupos — para clasificar grupos y para
    # elegir a los mejores terceros (no deben contaminarse con goles o
    # tarjetas de la eliminatoria, que es una fase posterior y ajena al
    # grupo ya cerrado).
    partidos_grupos = [p for p in matches if p.get("fase") == FASE_GRUPOS_TXT]
    stats_grupos = calcular_stats_globales(partidos_grupos)

    clasificaciones = {letra: clasificar_grupo(letra, matches, stats_grupos) for letra in GRUPOS}

    ranking_fifa = manual.get("ranking_fifa", {})
    if fase_grupos_terminada(matches):
        mejores_terceros, tabla_terceros = calcular_mejores_terceros(clasificaciones, stats_grupos, ranking_fifa)
    else:
        mejores_terceros, tabla_terceros = set(), []

    bonus_grupo = calcular_bonus_grupo(matches, clasificaciones, mejores_terceros)
    bonus_ronda = calcular_bonus_ronda(matches)
    premios = manual.get("premios_finales", {})
    goleador_equipo = manual.get("goleador_equipo") or None
    resultado = {}
    for eq in TODOS_LOS_EQUIPOS:
        s = stats[eq]
        pts_resultado = s["PtsResultado"]
        b_grupo = bonus_grupo.get(eq, 0)
        b_ronda_fases = bonus_ronda.get(eq, {fk: 0 for fk in FASES_KEYS.values()})
        b_ronda_total = sum(b_ronda_fases.values())
        premio_final = PUNTOS_PREMIO_FINAL.get(
            next((k for k, v in premios.items() if v == eq), None), 0
        )
        pts_goleador = PUNTOS_MAXIMO_GOLEADOR if goleador_equipo == eq else 0
        total = (
            s["GF"] * PUNTOS_GOL_FAVOR
            + s["GC"] * PUNTOS_GOL_CONTRA
            + s["TA"] * PUNTOS_TARJETA_AMARILLA
            + s["DA"] * PUNTOS_DOBLE_AMARILLA
            + s["RD"] * PUNTOS_ROJA_DIRECTA
            + s["PenFall"] * PUNTOS_PENALTI_FALLADO
            + s["PenPar"] * PUNTOS_PENALTI_PARADO
            + pts_resultado
            + b_grupo
            + b_ronda_total
            + premio_final
            + pts_goleador
        )
        fila = {
            "equipo": eq,
            "grupo": EQUIPO_A_GRUPO[eq],
            "bombo": EQUIPO_A_BOMBO[eq],
            "gf": s["GF"], "gc": s["GC"], "ta": s["TA"], "doblea": s["DA"], "rd": s["RD"],
            "penfall": s["PenFall"], "penpar": s["PenPar"],
            "bonus_resultado": pts_resultado,
            "bonus_grupo": b_grupo,
            "premio_final": premio_final,
            "goleador": pts_goleador,
            "puntos_totales": total,
        }
        for fase_key in FASES_KEYS.values():
            fila[f"bonus_ronda_{fase_key}"] = b_ronda_fases.get(fase_key, 0)
        resultado[eq] = fila
    return resultado, clasificaciones, tabla_terceros
# ─────────────────────────────────────────────────────────────────────────
# CONSTRUCCIÓN DE data.json (lo que consume el dashboard móvil)
# ─────────────────────────────────────────────────────────────────────────
def _partido_resumen(p: dict) -> dict:
    j = jugado(p)
    return {
        "id": p["id"],
        "fecha": p.get("fecha"),
        "fase": p.get("fase"),
        "grupo": p.get("grupo"),
        "local": p["local"],
        "visitante": p["visitante"],
        "gf_local": p.get("gf_local"),
        "gf_visit": p.get("gf_visit"),
        "ta_local": p.get("ta_local", 0), "doblea_local": p.get("doblea_local", 0), "rd_local": p.get("rd_local", 0),
        "ta_visit": p.get("ta_visit", 0), "doblea_visit": p.get("doblea_visit", 0), "rd_visit": p.get("rd_visit", 0),
        "pen_tanda_local": p.get("pen_tanda_local"),
        "pen_tanda_visit": p.get("pen_tanda_visit"),
        "jugado": j,
    }
def generar_data_json(matches: list[dict], manual: dict) -> dict:
    puntos, clasificaciones, tabla_terceros = calcular_puntos_totales(matches, manual)
    # --- Ranking general (ordenado, con posición ya calculada) ---
    ranking = sorted(puntos.values(), key=lambda d: d["puntos_totales"], reverse=True)
    for i, fila in enumerate(ranking, start=1):
        fila["pos"] = i
    # --- Partidos jugados (orden cronológico) ---
    jugados = [p for p in matches if jugado(p)]
    jugados.sort(key=lambda p: (p.get("fecha") or "", p["id"]))
    partidos_jugados = [_partido_resumen(p) for p in jugados]
    # --- Grupos: tabla + sus partidos (jugados y pendientes) ---
    grupos_out = {}
    for letra in GRUPOS:
        partidos_del_grupo = [
            _partido_resumen(p) for p in matches
            if p.get("grupo") == letra and p.get("fase") == FASE_GRUPOS_TXT
        ]
        partidos_del_grupo.sort(key=lambda p: (p.get("fecha") or "", p["id"]))
        grupos_out[letra] = {
            "equipos": GRUPOS[letra],
            "tabla": clasificaciones[letra],
            "partidos": partidos_del_grupo,
        }
    # --- Eliminatoria: partidos por fase ---
    eliminacion_out = {}
    for fase in FASES_ELIMINACION:
        partidos_fase = [
            _partido_resumen(p) for p in matches if p.get("fase") == fase
        ]
        partidos_fase.sort(key=lambda p: (p.get("fecha") or "", p["id"]))
        eliminacion_out[fase] = partidos_fase
    # --- Bombos con puntos actuales, ordenados de mayor a menor dentro de cada bombo ---
    bombos_out = {}
    for nombre, equipos in BOMBOS.items():
        fila = sorted(
            ({"equipo": eq, "puntos": puntos[eq]["puntos_totales"]} for eq in equipos),
            key=lambda d: d["puntos"], reverse=True,
        )
        bombos_out[nombre] = fila
    return {
        "meta": {
            "actualizado": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "total_partidos_jugados": len(jugados),
            "total_partidos": len(matches),
            "fase_grupos_terminada": fase_grupos_terminada(matches),
        },
        "ranking": ranking,
        "partidos": partidos_jugados,
        "grupos": grupos_out,
        "eliminacion": eliminacion_out,
        "bombos": bombos_out,
        "mejores_terceros": tabla_terceros,
        "premios_finales": manual.get("premios_finales", {}),
        "goleador_equipo": manual.get("goleador_equipo"),
    }

# ─────────────────────────────────────────────────────────────────────────
# IO helpers
# ─────────────────────────────────────────────────────────────────────────
def cargar_json(path: Path, default):
    if not Path(path).exists():
        return default
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)
def guardar_json(path: Path, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
def construir_y_guardar(matches_path: Path, manual_path: Path, salida_path: Path) -> dict:
    matches = cargar_json(matches_path, [])
    manual = cargar_json(manual_path, {"premios_finales": {}, "goleador_equipo": None, "ranking_fifa": {}})
    data = generar_data_json(matches, manual)
    guardar_json(salida_path, data)
    return data
if __name__ == "__main__":
    import sys
    base = Path(__file__).parent
    data = construir_y_guardar(
        base / "matches.json",
        base / "manual_overrides.json",
        base / "site" / "data.json",
    )
    print(f"data.json generado. Partidos jugados: {data['meta']['total_partidos_jugados']}")
