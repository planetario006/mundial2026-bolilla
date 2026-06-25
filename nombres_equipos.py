# -*- coding: utf-8 -*-
"""
nombres_equipos.py — Mundial 2026 · Bolilla
=============================================
Mapa único de traducción de nombres de equipo. Antes vivía duplicado
dentro de actualizar_mundial.py; se extrae aquí para que tanto el
scraper de Wikipedia como el de ESPN (espn_scraper.py) traduzcan al
mismo nombre canónico en español — el mismo que usa mundial_core.py en
GRUPOS/BOMBOS y el mismo que aparece en matches.json ("México",
"Sudáfrica", "Chequia", "EE.UU.", ...). Sin esto, fusionar resultados
de las dos fuentes por nombre de equipo no funcionaría nunca (un
"South Korea" de ESPN nunca matchearía con un "Corea del Sur" de
matches.json).
"""

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
    "Korea Republic": "Corea del Sur", "Republic of Korea": "Corea del Sur",
    "Czech Republic": "Chequia", "Czechia": "Chequia", "Canada": "Canadá",
    "Netherlands": "Países Bajos",
    "United States": "EE.UU.", "USA": "EE.UU.", "US": "EE.UU.",
    "Spain": "España", "Germany": "Alemania",
    "Brazil": "Brasil", "France": "Francia", "England": "Inglaterra",
    "Morocco": "Marruecos", "Croatia": "Croacia", "Belgium": "Bélgica",
    "Sweden": "Suecia", "Norway": "Noruega", "Tunisia": "Túnez",
    "Switzerland": "Suiza", "Saudi Arabia": "Arabia Saudí", "Turkey": "Turquía",
    "Türkiye": "Turquía", "Scotland": "Escocia", "Ivory Coast": "Costa de Marfil",
    "Côte d'Ivoire": "Costa de Marfil", "Cote d'Ivoire": "Costa de Marfil",
    "Egypt": "Egipto", "New Zealand": "Nueva Zelanda", "Algeria": "Argelia",
    "Qatar": "Catar", "Iraq": "Irak", "Panama": "Panamá",
    "Uzbekistan": "Uzbekistán", "Haiti": "Haití",
    "Iran": "Irán", "IR Iran": "Irán", "Jordan": "Jordania", "Japan": "Japón",
    "Cape Verde": "Cabo Verde", "Cabo Verde Islands": "Cabo Verde",
    "DR Congo": "R. D. Congo", "DR Congo (Zaire)": "R. D. Congo",
    "Congo DR": "R. D. Congo", "Bosnia and Herzegovina": "Bosnia",
    "Bosnia-Herzegovina": "Bosnia", "Curacao": "Curazao", "Curaçao": "Curazao",
}


def traducir(nombre: str) -> str:
    """Traduce un nombre de equipo (en cualquiera de los idiomas/formatos
    que usan Wikipedia o ESPN) al nombre canónico en español usado en
    matches.json y mundial_core.py. Si no está en el mapa, lo deja igual
    (mejor que perder el partido por una traducción que falta)."""
    n = (nombre or "").strip()
    return NOMBRE_MAP.get(n, n)
