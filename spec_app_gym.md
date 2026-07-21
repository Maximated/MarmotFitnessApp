# App de Entrenamiento de Gimnasio  Especificacin inicial

## Objetivo
App autoalojada, inspirada en Fitness Online, para registrar entrenamientos con
histrico de fechas, pesos, repeticiones y comentarios por serie. Proyecto tambin
usado para aprender a programar desde cero, paso a paso.

## Stack elegido (pensado para aprender + simplicidad)
- **Backend:** Python 3 + FastAPI
- **Base de datos:** PostgreSQL
- **Frontend (MVP):** plantillas Jinja2 renderizadas por el backend (sin JS framework
  todava; se puede migrar a React ms adelante si se desea)
- **Autenticacin:** OAuth 2.0 con Google, va Authlib
- **Despliegue:** Docker + docker-compose, detrs de BunkerWeb (igual que el resto
  del stack self-hosted del servidor)

## Modelo de datos (MVP)

User

id
google_id
email
name
created_at

Exercise

id
name
category (ej. "chest", "back"...)
target_muscle
equipment
gif_url
instructions

Routine # plantilla reutilizable, opcional

id
user_id (FK -> User)
name
created_at

RoutineExercise # ejercicios que componen una rutina, en orden

id
routine_id (FK -> Routine)
exercise_id (FK -> Exercise)
order

Workout

id
user_id (FK -> User)
routine_id (FK -> Routine, NULLABLE) # NULL = entrenamiento libre
date
notes

WorkoutSet

id
workout_id (FK -> Workout)
exercise_id (FK -> Exercise)
weight # en kilogramos (kg)
reps
comment
order (orden dentro del entrenamiento)


Notas de diseo:
- Los pesos se almacenan siempre en kg.
- Un `Workout` puede venir de una `Routine` (rutina predefinida) o no (`routine_id` NULL = entrenamiento libre). Ambos flujos conviven.
- Las grficas de progreso se calculan a partir del histrico de `WorkoutSet` agrupado por `exercise_id` a lo largo del tiempo (no requieren tabla propia).

## Origen de datos de ejercicios
Dataset: https://github.com/hasaneyldrm/exercises-dataset
- 1.324 ejercicios con nombre, categora, msculo objetivo, equipo, instrucciones y GIF animado
- Formato: JSON (`data/exercises.json`) + carpetas `images/` y `videos/` (gifs)
- **Licencia: uso educativo/personal, NO comercial.** Vlido para este proyecto
  siempre que se quede en uso personal.
- Plan de importacin: script que lee `exercises.json` e inserta en la tabla `Exercise`,
  copiando los gifs/imgenes a un volumen del servidor servido como estticos.

## Funcionalidades MVP (en orden de construccin sugerido)
1. Login con Google (OAuth) y creacin de usuario en la BD
2. Importar el dataset de ejercicios a la base de datos
3. Listado/buscador de ejercicios (nombre, categora, equipo) con su gif
4. Crear un entrenamiento nuevo, libre (fecha + notas)
5. Aadir series a un entrenamiento (ejercicio + peso en kg + reps + comentario)
6. Histrico: ver entrenamientos pasados, filtrables por fecha o por ejercicio
7. Rutinas: crear una rutina (plantilla con lista de ejercicios) y arrancar un
   entrenamiento a partir de ella
8. Grficas de progreso: evolucin de peso/reps de un ejercicio a lo largo del tiempo

## Fuera del MVP (fases futuras, no ahora)
- Frontend ms rico (React/SPA)
- Contador de caloras / planes de dieta (descartado, no lo quiere)
- App mvil / PWA

## Cmo continuar
Este documento se pasa como punto de partida a **Claude Code** (terminal, IDE o
app de escritorio). Ah se inicializa el repositorio y se construye paso a paso,
empezando por el punto 1 de las funcionalidades MVP.
