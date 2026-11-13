# Registro de uso de IA (declaracion para el informe)
| Fecha | Etapa | Ayuda de Claude | Decision / revision del grupo |
|---|---|---|---|
| 2026-11-13 | Planificacion | Propuso alcance, fuentes, criterio de brecha, arquitectura y hosting | Grupo aprobo defaults (Hype Cycle como estimacion propia, 3 horizontes, escala 0-5, espanol) |
| 2026-11-13 | Etapa 1 | Escribio `collect.py` y `sources.json` (codigo) y pruebas con ejemplos | PENDIENTE: grupo revisa lista de fuentes y corre el recolector |
## Limitaciones observadas
- El entorno de Claude no puede llamar a PubMed/ClinicalTrials/etc. (politica de red); el recolector se prueba con ejemplos y corre en la PC del grupo.
- URLs de ANMAT/CONICET sin confirmar: dejadas deshabilitadas, no inventadas.
| 2026-11-13 | Etapa 2 | Claude escribió `process.py` (filtro, extracción con Gemini, verificación) y `taxonomy.json`; diagnosticó la elección de modelo preview y el defecto del prompt de horizontes | Grupo corrió el cuaderno en Colab con su clave y compartió los resultados; decidió pasar a GitHub y página propia |
| 2026-11-13 | Infra | Claude preparó el repositorio de GitHub y subió el código | Grupo creó la cuenta y el repositorio y dio los permisos |
