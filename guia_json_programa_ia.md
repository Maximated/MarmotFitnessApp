# Guía para generar un programa de entrenamiento en JSON (MarmotFitnessApp)

Este documento está pensado para dárselo a una IA junto con el catálogo de
ejercicios (ver más abajo) y pedirle que genere un `.json` importable desde
"Nuevo programa → Importar desde JSON" en la app. Describe **exactamente**
los campos que el importador (`app/program_import.py`) lee — cualquier otro
campo que se añada es simplemente ignorado, no da error.

## 1. Catálogo de ejercicios: de dónde sacar nombres e id_dataset

El catálogo completo vive en dos archivos del repositorio, en inglés más un
diccionario de traducción al español:

- `data/exercises.json` — 1324 ejercicios, cada uno con un campo `"id"`
  (string de 4 dígitos, ej. `"0001"`) que es el identificador estable.
- `data/translations_es.json` — su clave `"name"` es un diccionario
  `{ "id_del_ejercicio": "nombre en español" }` con el nombre TAL CUAL se
  guarda en la base de datos y se muestra en la app (el nombre en
  `exercises.json` está en inglés, ese no es el que usa la app).

**Para generar el JSON, adjunta a la IA el diccionario `"name"` de
`data/translations_es.json`** (o un extracto relevante) — así puede elegir
`id_dataset` reales y escribir el `nombre` exactamente como existe en la
base de datos. Si no tienes ese archivo a mano, también puedes pedir a la
IA que use nombres razonables y dejar que el importador los resuelva por
similitud (ver sección 2) — pero id_dataset exacto es siempre más fiable.

Valores reales que existen en el catálogo (para dar contexto, no se
escriben directamente en el JSON del programa salvo `muscle_group`, que es
libre):

- **category**: abdomen, antebrazos, brazos, cardio, cuello, espalda,
  hombros, pantorrillas, pecho, piernas
- **target_muscle**: abdominales, abductores, aductores, antebrazos,
  bíceps, columna, cuádriceps, deltoides, dorsales, elevador de la
  escápula, espalda alta, gemelos, glúteos, isquiotibiales, pectorales,
  serrato anterior, sistema cardiovascular, trapecios, tríceps
- **equipment**: asistido, balón medicinal, banda, banda elástica, barra,
  barra hexagonal, barra olímpica, barra Z, bicicleta estática, bosu, con
  peso, cuerda, elíptica, ergómetro de brazos, escaladora, fitball,
  mancuerna, máquina de palanca, máquina hammer, máquina skierg, máquina
  smith, neumático, pesa rusa, peso corporal, polea, rodillo, rueda
  abdominal, trineo

## 2. Cómo se empareja cada ejercicio con el catálogo

Por cada ejercicio del JSON, el importador prueba en este orden:

1. Si `id_dataset` viene con un valor (string o número), lo compara contra
   el `id` del catálogo (rellenado a 4 dígitos, ej. `7` → `"0007"`). Si
   coincide, listo — este es el método más fiable, úsalo siempre que
   sepas el id real.
2. Si no hay match por id (o no se dio `id_dataset`), compara `nombre` con
   los alias ya confirmados y luego con el nombre exacto normalizado
   (mayúsculas/acentos no importan).
3. Si tampoco hay coincidencia exacta, busca por similitud difusa; si la
   similitud es ≥90%, lo empareja igualmente.
4. Si nada de lo anterior encuentra nada, el ejercicio queda **"pendiente
   de resolver"**: se crea igualmente en el programa, pero sin catálogo
   (sin gif), y en la pantalla de importación aparece un enlace para
   vincularlo a mano más tarde.

### Ejercicios A PROPÓSITO sin catálogo

Si un ejercicio no tiene equivalente real en el catálogo (p. ej. un
estiramiento o movimiento inventado que no está en la base de datos), NO
lo dejes para que caiga en "pendiente" — dilo explícitamente poniendo la
clave `id_dataset` con valor `null` (no la omitas, ponla a `null`
literalmente). Eso hace que el importador lo cree directamente sin
catálogo, sin pasar por el emparejador ni aparecer como pendiente. Se
mostrará en la app con el `nombre` que le hayas dado y un icono
genérico en vez de gif, pero funciona exactamente igual (series o tiempo,
registro de series, historial...).

Si simplemente **omites** la clave `id_dataset` (no la escribes), el
importador SÍ intentará emparejarlo por nombre — solo un `id_dataset: null`
explícito lo salta.

## 3. Estructura del JSON

```json
{
  "programa": "Nombre del programa",
  "jornadas": [
    {
      "nombre": "Subtítulo del día (opcional, ej. 'Empuje')",
      "bloques": [
        {
          "tipo": "calentamiento",
          "descanso_segundos": 0,
          "ejercicios": [
            { "nombre": "elíptica", "id_dataset": "0345", "modo": "tiempo", "duracion_segundos": 300 }
          ]
        },
        {
          "tipo": "grupo_muscular",
          "muscle_group": "Pecho",
          "variante": "alto",
          "num_sets": 3,
          "descanso_segundos": 90,
          "ejercicios": [
            { "nombre": "press de banca inclinado en polea", "id_dataset": "0169", "reps_min": 8, "reps_max": 10 },
            { "nombre": "aperturas en polea", "id_dataset": "0201", "reps_min": 10, "reps_max": 12, "superset_con": "A" },
            { "nombre": "flexiones", "id_dataset": null, "reps_min": 10, "reps_max": 15, "superset_con": "A" }
          ]
        }
      ]
    }
  ]
}
```

### Nivel programa (raíz)

| Campo      | Obligatorio | Tipo   | Notas                                         |
|------------|-------------|--------|------------------------------------------------|
| `programa` | Sí          | string | Nombre del programa.                           |
| `jornadas` | Sí          | array  | Al menos 1. El número de días del ciclo se calcula automáticamente como `len(jornadas)` — no hace falta (ni se lee) un campo aparte tipo `ciclo_dias`. |

Cualquier otra clave a este nivel se ignora.

### Cada jornada (día del ciclo)

| Campo     | Obligatorio | Tipo   | Notas                                                       |
|-----------|-------------|--------|---------------------------------------------------------------|
| `nombre`  | No          | string | Subtítulo del día (ej. "Empuje", "Tirón"). Se muestra junto al número de día. |
| `bloques` | No          | array  | El número de día (Día 1, Día 2...) es su posición en el array `jornadas`, no un campo propio. |

### Cada bloque (agrupa ejercicios dentro de una jornada, con su propio descanso)

| Campo                | Obligatorio | Tipo         | Notas |
|-----------------------|-------------|--------------|-------|
| `tipo`                | No          | string       | `"calentamiento"`, `"grupo_muscular"`, `"cardio"` o `"estiramiento"` se traducen a su forma bonita (Calentamiento, Grupo muscular...); cualquier otro texto se usa capitalizado tal cual. |
| `muscle_group`        | No          | string       | Texto libre (ej. "Pecho", "Espalda"). Solo informativo. |
| `variante`             | No          | string       | Texto libre (ej. "alto", "declinado"). Solo informativo. |
| `num_sets`             | No          | int          | Nº de series objetivo para TODO el bloque (se usa para calcular el % de progreso). Déjalo fuera en calentamiento/estiramiento. |
| `descanso_segundos`    | No          | int          | Descanso entre series, **para todo el bloque** (no hay descanso por ejercicio individual). Si se omite, es 0. |
| `ejercicios`           | No          | array        | Orden = orden de aparición en pantalla. |

### Cada ejercicio

| Campo               | Obligatorio | Tipo             | Notas |
|----------------------|-------------|------------------|-------|
| `nombre`              | Sí          | string           | Nombre a mostrar / usar para emparejar. |
| `id_dataset`          | No          | string, int o `null` | Ver sección 2. Omitir ≠ `null`: cambia el comportamiento. |
| `modo`                | No          | `"series"` o `"tiempo"` | Por defecto `"series"`. |
| `reps_min` / `reps_max` | Solo si `modo` es `"series"` (u omitido) | int | Rango de repeticiones objetivo. Pueden ser iguales. |
| `duracion_segundos`   | Solo si `modo` es `"tiempo"` | int | Segundos objetivo del ejercicio (no confundir con el descanso del bloque). |
| `superset_con`        | No          | string (una letra o etiqueta) | Ver más abajo. |

**Superserie**: para emparejar dos ejercicios CONSECUTIVOS del mismo
bloque como superserie (se hacen seguidos, sin descanso entre ellos), pon
el mismo valor de `superset_con` en ambos (ej. `"A"`) y nada o un valor
distinto en el resto. Debe ser exactamente una pareja de dos — no uses el
mismo valor en tres o más ejercicios seguidos, el comportamiento no está
pensado para eso.

## 4. Notas finales

- Importar un JSON crea un programa **nuevo**; no actualiza uno existente.
  Para reemplazar un programa, importa el nuevo y borra el antiguo desde
  la app.
- Después de importar, la pantalla de resultado muestra cuántos
  ejercicios se emparejaron por id/nombre/similitud, cuántos se marcaron
  a propósito sin catálogo, y cuántos quedaron pendientes de resolver a
  mano.
- El peso objetivo (`target_weight`) no se configura desde el JSON — se
  ajusta después, ya dentro de la app, editando el ejercicio dentro del
  bloque.
