# Mundial 2026 · La Bolilla — app de móvil

App de móvil (web instalable, PWA) que muestra siempre actualizado, para
todos los que participáis en la bolilla:

- **Ranking** general, con el desglose de puntos al tocar cada fila.
- **Partidos** jugados, agrupados por fecha.
- **Grupos** (A-L), con su tabla de clasificación y los partidos de cada uno.
- **Eliminatoria** (dieciseisavos → final), con los cruces ya jugados.
- **Bombos** del sorteo, con los puntos actuales de cada equipo.

Se actualiza sola cada 30 minutos leyendo Wikipedia, sin que nadie tenga
que ejecutar nada a mano ni tener Excel/Windows abierto. Tu Excel de
escritorio (`Mundial2026_Puntuacion.xlsm`) lo puedes seguir usando
exactamente igual que hasta ahora si quieres — este proyecto es
independiente y parte de la misma fuente (Wikipedia), no lo sustituye.

---

## Cómo está organizado

```
actualizar_mundial.py      → descarga resultados de Wikipedia y actualiza matches.json
mundial_core.py            → calcula clasificaciones (desempates FIFA), puntos y bombos
matches.json                → "base de datos" de partidos (se versiona en git)
manual_overrides.json       → premios finales y máximo goleador (se edita a mano, un par de veces en todo el torneo)
site/
  index.html                 → la app (todo en un único fichero, sin build)
  data.json                   → la "foto" que consume la app (se regenera sola)
  manifest.json, sw.js, icons/ → para que se pueda instalar como app
.github/workflows/actualizar.yml → la automatización (GitHub Actions)
README.md                  → este documento
```

## Qué necesitas antes de empezar

- Una cuenta de **GitHub** (gratis, en [github.com](https://github.com)).
- Nada más. No hace falta instalar nada en tu ordenador ni saber programar.

---

## Puesta en marcha, paso a paso (~10 minutos, una sola vez)

### 1. Descomprime el `.zip`

Tendrás una carpeta `mundial2026-bolilla` con todos los ficheros de arriba.

### 2. Personaliza el contacto del User-Agent

Abre `actualizar_mundial.py` con cualquier editor de texto, busca esta línea
cerca del principio del fichero:

```python
CONTACTO = "https://github.com/TU-USUARIO/TU-REPO"  # <-- CAMBIA ESTO
```

Wikimedia exige que toda herramienta automatizada se identifique con un
contacto real. Cámbialo ahora por la URL que va a tener tu repositorio
(la decides tú en el siguiente paso, puedes volver aquí después si
prefieres) o por tu email. Es el único cambio obligatorio antes de subirlo.

### 3. Crea el repositorio en GitHub

En github.com → botón **New repository** → nombre, por ejemplo
`mundial2026-bolilla` → marca **Public** (tiene que ser público para que
GitHub Pages lo sirva gratis sin complicaciones) → **Create repository**,
sin añadir README ni licencia (ya llevas los tuyos).

### 4. Sube los ficheros

La forma más sencilla, sin instalar nada:

- En la página del repositorio recién creado, click en **uploading an
  existing file** (o **Add file → Upload files**).
- Arrastra **todo el contenido** de la carpeta `mundial2026-bolilla`
  (los ficheros y las carpetas `site/` y `.github/` tal cual, manteniendo
  su estructura).
- Baja y dale a **Commit changes**.

> Si te manejas con git, la alternativa clásica también vale:
> ```
> cd mundial2026-bolilla
> git init
> git add .
> git commit -m "Primera subida"
> git branch -M main
> git remote add origin https://github.com/TU-USUARIO/TU-REPO.git
> git push -u origin main
> ```

### 5. Activa GitHub Pages

**Settings → Pages** → en "Build and deployment / Source" elige
**Deploy from a branch** → rama `main`, carpeta **`/site`** → **Save**.

Al cabo de 1-2 minutos tu app estará en:

```
https://TU-USUARIO.github.io/TU-REPO/
```

Esa es la URL que vas a compartir con el resto de la bolilla.

### 6. Da permiso de escritura a las Actions

**Settings → Actions → General** → baja hasta **"Workflow permissions"** →
marca **"Read and write permissions"** → **Save**. Sin esto, el robot que
actualiza los datos no podrá guardar los cambios.

### 7. Lanza la primera actualización a mano

Pestaña **Actions** → **"Actualizar Mundial 2026"** → **"Run workflow"** →
**Run workflow** (de nuevo, para confirmar). Espera 1-2 minutos y comprueba:

- El círculo del workflow se pone en ✅ verde (no en ❌ rojo).
- Aparece un commit nuevo del autor `mundial-bot`.
- Si entras en `site/data.json` desde GitHub, el campo `"actualizado"` tiene
  la fecha/hora de ahora mismo.

### 8. Compruébalo en el móvil

Abre la URL del paso 5 en el navegador del móvil. Para que quede como una
app de verdad: menú del navegador → **"Añadir a pantalla de inicio"**
(Android/Chrome) o **"Compartir → Añadir a inicio"** (iPhone/Safari).
Comparte el enlace con el resto de la bolilla — todos veis la misma app,
no hace falta que cada uno la instale ni configure nada.

A partir de aquí no hay que tocar nada más: el workflow corre solo cada 30
minutos.

---

## Si algo no carga (comprobaciones rápidas)

| Síntoma | Causa probable |
|---|---|
| La URL de Pages da 404 | El paso 5 aún no ha terminado de desplegar (espera 1-2 min) o la carpeta elegida no es `/site` |
| La app carga pero dice "No se pudo cargar data.json" | El workflow del paso 7 aún no se ha ejecutado ni una vez, o falló — revisa la pestaña Actions |
| El workflow termina en ❌ rojo | Abre el log del paso que falló; si es "Permission denied" al hacer `git push`, revisa el paso 6 |
| Los datos no cambian nunca | Comprueba en Actions que el workflow se sigue ejecutando cada 30 min (GitHub a veces pausa workflows en repos muy inactivos; un "Run workflow" manual lo reactiva) |

---

## Lo único que sigue siendo manual (y por qué)

- **Penaltis fallados/parados** (`penfall_*` / `penpar_*` dentro de cada
  partido en `matches.json`): Wikipedia no los recoge de forma fiable, así
  que el sistema nunca los toca solo — igual que en el Excel original,
  donde eran las "columnas amarillas". Para anotarlos: abre `matches.json`
  en GitHub (icono del lápiz ✏️), busca el partido y cambia el número.
  Se puede hacer desde el navegador del móvil.
- **Premios finales y máximo goleador** (`manual_overrides.json`): se
  rellenan al final del torneo (campeón, subcampeón, 3º, 4º, máximo
  goleador). Mismo procedimiento: editar el fichero en GitHub.

En ambos casos, en cuanto guardas el cambio (commit), la siguiente
ejecución del robot —o un "Run workflow" manual— recalcula todo y la app
se actualiza para todo el grupo.

---

## Sobre las peticiones a Wikipedia (para que no os bloqueen)

Cada actualización completa revisa **17 páginas** (12 grupos + 5 fases
eliminatorias). Con el workflow cada 30 minutos son unas **34
peticiones/hora**, muy por debajo de cualquier límite de Wikimedia — pero
sus reglas se endurecieron en 2026 con tráfico no identificado, así que el
sistema sigue estas prácticas:

- **User-Agent con contacto real** (el paso 2 de arriba) — sin él,
  Wikimedia puede meterte en el nivel más bajo de su límite (500/hora) en
  vez de tratarte como herramienta identificada.
- **Una sola petición a la vez**, ~1 segundo de pausa entre página y
  página (Wikimedia recomienda no superar 3 en paralelo ni 5/segundo).
- **Reintentos con espera progresiva** ante "demasiadas peticiones" (429)
  o "servidor saturado" (503/maxlag): respeta `Retry-After` si el servidor
  lo manda, y si no, espera de forma creciente (2s, 4s, 8s, 16s).
- **Degradación correcta**: si una página sigue sin responder tras los
  reintentos, se anota como "no disponible esta vez" y el resto de la
  actualización sigue con normalidad — se recupera sola 30 min después.
- **Sin ejecuciones solapadas**: el workflow tiene `concurrency`
  activado, así que nunca hay dos actualizaciones a la vez.

Si alguna vez veis 429 persistentes pese a todo esto (muy improbable a
este volumen), la solución con más margen es autenticar las peticiones con
un [token personal de la API de Wikimedia](https://api.wikimedia.org/wiki/Documentation/Getting_started/Authentication) — pero para 17 páginas cada 30
minutos no debería hacer falta.

---

## Notas técnicas sobre la migración

Al revisar el proyecto original encontré y corregí dos cosas antes de
automatizar:

1. El script de escritorio llamaba a una macro `ActualizarPosiciones` que
   no existe en el libro (las macros reales se llaman
   `ActualizarClasificacion` y `ActualizarPuntosBombos`), así que
   probablemente llevaba tiempo fallando en silencio. Aquí no aplica
   porque la clasificación y los bombos se calculan directamente en
   Python (`mundial_core.py`), réplica fiel de la lógica de desempate
   FIFA del Excel, verificada contra los datos reales del torneo (mismo
   orden de grupos, mismos puntos).
2. La lista de grupos del script original cubría A-K (11 grupos) y se
   dejaba fuera el Grupo L. Aquí están los 12.

*(Si quieres seguir usando también el Excel de escritorio en local, hay
una versión corregida de `actualizar_mundial_wikipedia.py` y del módulo
`ClasificacionMundial2026.bas` que resuelve estos dos puntos ahí también —
son ficheros aparte, no forman parte de este repositorio.)*
