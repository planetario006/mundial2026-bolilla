# team_names.py
# -*- coding: utf-8 -*-
"""Diccionario único de nombres de selección, compartido entre la fuente
Wikipedia y la fuente ESPN. Si en el futuro ESPN devuelve un nombre que no
está aquí, añádelo en este archivo — es el único sitio donde hace falta."""

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
    "Czech Republic": "Chequia", "Canada": "Canadá", "Netherlands": "Países Bajos",
    "United States": "EE.UU.", "USA": "EE.UU.", "Spain": "España", "Germany": "Alemania",
    "Brazil": "Brasil", "France": "Francia", "England": "Inglaterra",
    "Morocco": "Marruecos", "Croatia": "Croacia", "Belgium": "Bélgica",
    "Sweden": "Suecia", "Norway": "Noruega", "Tunisia": "Túnez",
    "Switzerland": "Suiza", "Saudi Arabia": "Arabia Saudí", "Turkey": "Turquía",
    "Scotland": "Escocia", "Ivory Coast": "Costa de Marfil", "Egypt": "Egipto",
    "New Zealand": "Nueva Zelanda", "Algeria": "Argelia", "Qatar": "Catar",
    "Iraq": "Irak", "Panama": "Panamá", "Uzbekistan": "Uzbekistán", "Haiti": "Haití",
    "Iran": "Irán", "Jordan": "Jordania", "Japan": "Japón", "Cape Verde": "Cabo Verde",
    "DR Congo": "R. D. Congo",
}

def traducir(nombre: str) -> str:
    n = nombre.strip()
    return NOMBRE_MAP.get(n, n)
