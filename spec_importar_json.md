## Especificación: importador de programas desde JSON

### Dónde va
En la pantalla de creación de programas, añadir un botón "Importar programa desde JSON"
como alternativa a crearlo a mano. Al pulsarlo, el usuario sube un archivo .json.

### Formato de entrada esperado
El JSON tiene esta forma (ejemplo real ya generado: programa_empuje_tiron_pierna.json):

```json
{
  "programa": "nombre del programa",
  "ciclo_dias": 3,
  "total_jornadas": 30,
  "jornadas": [
    {
      "numero_jornada": 1,
      "nombre": "Empuje (ciclo 1) — pecho alto",
      "bloques": [
        {
          "tipo": "grupo_muscular",
          "muscle_group": "Pecho",
          "variante": "alto",
          "descanso_segundos": 120,
          "num_sets": 3,
          "ejercicios": [
            { "nombre": "press de banca inclinado con barra", "id_dataset": "0169",
              "reps": "8-10", "superset_con": null }
          ]
        }
      ]
    }
  ]
}
```

### Lógica de importación (por este orden de prioridad)

1. **Emparejar por `id_dataset` contra `Exercise.external_id`** — es el caso normal,
   ya que los JSON que generamos incluyen el id original del catálogo. Si hay
   coincidencia exacta, usar ese `Exercise` directamente, sin más comprobación.

2. **Si no hay `id_dataset` o no coincide con ningún `external_id`** (por ejemplo,
   si el JSON lo ha escrito el usuario a mano con solo el nombre): buscar por
   `nombre` normalizado (minúsculas, sin tildes, espacios recortados) contra
   `Exercise.name`.

3. **Si tampoco hay coincidencia exacta de nombre**: usar coincidencia difusa
   (fuzzy matching, librería `rapidfuzz` en Python) contra `Exercise.name` y
   quedarse con el candidato más parecido.

4. **Nunca importar en silencio una coincidencia dudosa.** Si el mejor resultado
   del fuzzy matching tiene menos de, por ejemplo, un 90% de similitud, el
   ejercicio se marca como "pendiente de confirmar" en un informe final, en vez
   de asumir que es correcto.

5. **Informe post-importación**: al terminar, mostrar al usuario un resumen:
   cuántos ejercicios se importaron por id exacto, por nombre exacto, por fuzzy
   matching (con el % de similitud), y cuáles quedaron sin resolver y necesitan
   que el usuario elija manualmente el ejercicio correcto de una lista desplegable.

6. **Tabla de alias** (`ExerciseAlias`: nombre_usado → exercise_id): cuando el
   usuario confirma manualmente una coincidencia (sea del fuzzy matching o de la
   lista desplegable), guardar esa asociación aquí. En futuras importaciones,
   comprobar esta tabla ANTES que el fuzzy matching — si el nombre ya tiene un
   alias guardado, usarlo directamente sin volver a preguntar.

7. **Crear las entidades**: por cada jornada del JSON, crear un `DayTemplate`
   (usando `numero_jornada` como `day_number`) con sus `Block` y `BlockExercise`
   correspondientes, todos asociados al `Program` nuevo (`cycle_days` =
   `total_jornadas` del JSON, o el que corresponda).

8. **Transacción atómica**: si algo falla a mitad de la importación, no debe
   quedar el programa a medias en la base de datos — o se importa todo, o no se
   importa nada (rollback).

### Casos límite a manejar
- JSON con un `Block` sin ningún ejercicicio resuelto (todos pendientes): el
  programa se crea igualmente, pero ese bloque queda marcado visualmente como
  incompleto hasta que el usuario resuelva sus pendientes.
- Bloques de tipo "calentamiento" o "estiramiento" con campo `nota` en vez de
  `ejercicios`: no requieren emparejamiento con el catálogo, se guardan como
  texto libre.