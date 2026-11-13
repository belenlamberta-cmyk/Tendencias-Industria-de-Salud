# Tendencias-Industria-de-Salud

Radar de tendencias tecnológicas para laboratorios de investigación en salud/biotecnología (tipo CONICET).
Trabajo práctico universitario: un agente que recolecta fuentes públicas, identifica tendencias, verifica cada dato contra el texto original y alimenta un tablero público.

## Estado
- Recolección: `agent/collect.py` · Filtro y verificación: `agent/process.py` · Reglas: `agent/rules.py` + `agent/catalog.json` · Exportación: `agent/export.py`
- Tablero: `docs/index.html` (GitHub Pages) · Ejecución diaria: `.github/workflows/daily.yml`
- Cuaderno de Colab para pruebas: `notebooks/radar_salud_colab_v4.ipynb`
- Pendiente: mapa de brechas con puntajes revisados, inversión, regulación por país y fuentes argentinas.

Las claves de API **nunca** van en este repositorio (se guardan como secretos).

## Cómo ver el tablero
Abrir la página pública (GitHub Pages): https://belenlamberta-cmyk.github.io/Tendencias-Industria-de-Salud/ — no requiere cuenta ni clave.

## Cómo volver a ejecutar el agente (no requiere claves ni instalar nada)
Hace falta solo Python 3.12 (usa la biblioteca estándar).

```bash
git clone https://github.com/belenlamberta-cmyk/Tendencias-Industria-de-Salud.git
cd Tendencias-Industria-de-Salud
python agent/collect.py --days 30        # 1. recolecta fuentes públicas
python agent/process.py filter --max 250 # 2. filtra lo relevante
python agent/rules.py                    # 3. identifica tendencias por reglas (sin IA)
python agent/process.py verify           # 4. verifica cada cita contra el texto original
python agent/export.py                   # 5. genera docs/data/trends.json (lo lee la página)
python -m http.server -d docs 8000       # abrir http://localhost:8000
```
En GitHub, la pestaña Actions → "Actualización diaria del radar" → Run workflow ejecuta lo mismo (requiere permiso de escritura en el repositorio). Además corre sola todos los días a las 06:23 (hora de Argentina).

## Qué es IA y qué no
- La actualización diaria usa **reglas y un catálogo** (`agent/catalog.json`), no IA generativa.
- Opcionalmente, un modelo de IA puede analizar documentos y guardar sus resultados en `data/processed/`; en ese caso cada tendencia lo indica en el campo "Método". Todo pasa por el mismo verificador.
- Registros para el informe: `informe/registro_uso_ia.md` y `informe/registro_errores_ia.md`.
