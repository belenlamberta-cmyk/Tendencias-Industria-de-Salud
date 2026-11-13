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
| 2026-11-13 | Etapa 2b | Claude escribió `rules.py` y `catalog.json` (clasificador por reglas sin IA, catálogo cerrado de 35 tecnologías) porque la cuota gratuita de Gemini se agotaba y los modelos devolvían errores 503/429 | Grupo pidió la alternativa; debe revisar el catálogo y las reglas de horizonte/fase (heurísticas, no Gartner) |
| 2026-11-13 | Decisión | El grupo decidió sacar Gemini del flujo diario por inestabilidad (503/429/404) y dejar solo el clasificador por reglas; el código de Gemini queda en el repositorio como opción manual | Decisión del grupo; debe justificarse en el informe frente a la consigna de "agente de IA" |
| 2026-11-13 | Análisis con Claude | A pedido del grupo, Claude leyó 19 documentos seleccionados (diversidad de fuentes y 1 con afiliación argentina) y propuso 14 tendencias con cita textual; 7 documentos se registraron sin tendencia por falta de relevancia. Archivo: `data/processed/extractions_claude.jsonl` | Las 14 pasaron el verificador automático (0 descartes). El grupo debe revisar el criterio de selección y las fases/horizontes asignados (juicio de la IA) |

| 2026-11-13 | Mapa de brechas | Claude propuso 8 tecnologías y asignó adopción (0–5) y madurez esperada (corto/mediano/largo) con justificación y fuentes de búsquedas web; 7 con puntaje, 1 "sin fuente suficiente". Se publicó en `docs/data/gaps.json` (copia de `agent/gaps.json`). | Puntajes = estimación de Claude, marcados "pendiente de revisión" hasta que la persona responsable los apruebe. |
