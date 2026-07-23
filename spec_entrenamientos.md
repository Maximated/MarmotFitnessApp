## Especificación: motor de programas de entrenamiento

### Concepto general
Un "Programa" (ej. "Brazos") no es una lista fija de 40 jornadas con ejercicios
concretos. Es una PLANTILLA CÍCLICA que genera la jornada concreta cuando toca.

### Estructura de datos necesaria

**Programa**
- id, nombre (ej. "Brazos")
- número de días en el ciclo (ej. 4)

**PlantillaDeDia** (una por cada día del ciclo, ej. día 1 a 4)
- id, programa_id, número de día dentro del ciclo
- lista ordenada de Bloques

**Bloque** (una unidad dentro de una jornada: calentamiento, abdomen, un grupo
muscular, estiramientos...)
- id, plantilla_dia_id, tipo (calentamiento / abdomen / grupo_muscular / estiramiento)
- grupo_muscular (si aplica: pecho, espalda, bíceps, tríceps, hombro, pierna, pantorrilla)
- variante (si aplica, ej. "pecho_alto" vs "pecho_bajo" — para la rotación)
- número de ejercicios que contiene
- descanso_segundos: tiempo de descanso a aplicar entre series de este bloque
  (ej. 120 para bloques normales de brazos, 60 para el bloque de abdomen)
- es_superset: true/false
- si es_superset, los ejercicios del bloque van emparejados de 2 en 2

**ReglaDeRotacion**
- Cuando se genera una jornada real y toca un bloque con "variante" (ej. pecho),
  el sistema mira cuál fue la última variante de ese grupo muscular usada por el
  usuario y elige la otra (o la siguiente en la rotación si hay más de 2).
- Esto se resuelve en tiempo de generación de la jornada, no se guarda fijo en la
  plantilla.

**JornadaGenerada** (lo que el usuario ve y realiza un día concreto)
- Se genera a partir de una PlantillaDeDia + la ReglaDeRotacion + selección de
  ejercicios concretos del catálogo (Exercise) que cumplen el grupo_muscular/variante
  del bloque.
- Cada ejercicio de la jornada generada puede sustituirse por otro del mismo
  grupo_muscular usando el botón de "ejercicio similar" (busca en la tabla Exercise
  por el mismo grupo_muscular, sin cambiar el resto de la jornada).

### Cronómetro de descanso

- Cada Bloque tiene su propio `descanso_segundos` (ver arriba) — NO es un valor
  global de la app, varía por bloque (ej. 120s en bloques normales, 60s en abdomen).
- El cronómetro se activa automáticamente al registrar/guardar una serie
  (WorkoutSet) dentro de ese bloque.
- EXCEPCIÓN — superseries: si el bloque es superset (dos ejercicios emparejados),
  el cronómetro NO se activa al guardar la serie del primer ejercicio del par,
  solo al guardar la serie del SEGUNDO ejercicio del par. Es decir, el descanso
  se cuenta después de completar el par completo, no después de cada ejercicio
  individual.
- Al llegar a 0, debe lanzar una notificación (notificación del navegador/sistema,
  no solo un aviso visual dentro de la app, porque el usuario puede no estar
  mirando la pantalla entre series).

  ### Ejercicios similares (componente reutilizable, no exclusivo del entrenamiento)

- La función de "ver ejercicios similares" pertenece al catálogo de Exercise,
  no al modo entrenamiento. Debe comportarse EXACTAMENTE igual en dos contextos:
  1. Navegando el catálogo de ejercicios desde la página principal (fuera de
     cualquier entrenamiento)
  2. Dentro de una JornadaGenerada, en modo entrenamiento activo

- En ambos casos la lógica es la misma: dado un Exercise, buscar otros Exercise
  con el mismo grupo_muscular (y opcionalmente mismo patrón de movimiento/equipo)
  y mostrarlos como alternativas.

- La diferencia entre los dos contextos es solo QUÉ PASA al elegir una alternativa:
  - Desde el catálogo (fuera de entrenamiento): simplemente navegas a la ficha
    del ejercicio elegido, no afecta a nada más.
  - Dentro de una jornada activa: al elegir la alternativa, sustituye a ese
    ejercicio dentro de la JornadaGenerada actual (la serie que se registre a
    partir de ahí se guarda contra el ejercicio nuevo, no el original).

- Recomendación de implementación: construir "ejercicios similares" como un
  componente/función independiente y reutilizable (recibe un exercise_id, 
  devuelve una lista de alternativas), y que tanto la ficha de ejercicio del
  catálogo como la vista de jornada activa lo consuman igual, cada una
  gestionando después su propio "qué hacer al elegir uno".

### Fases de construcción sugeridas
1. Modelo de datos: Programa → PlantillaDeDia → Bloque, con ejercicios fijos
   (sin rotación todavía)
2. Añadir variante + ReglaDeRotacion
3. Añadir superseries (emparejar ejercicios de 2 en 2 dentro de un bloque)
4. Añadir botón de "ejercicio similar"
5. Añadir cronómetro de descanso con su lógica de superseries + notificación
6. (Aparte, no ahora) Sesión de investigación para definir descanso_segundos y
   series/repeticiones de cada bloque según evidencia científica reciente





