# Tendencias-Industria-de-Salud

Radar de tendencias tecnológicas para laboratorios de investigación en salud/biotecnología (tipo CONICET).
Trabajo práctico universitario: un agente de IA que recolecta fuentes verificables, extrae tendencias con un modelo de lenguaje, verifica cada dato contra el texto crudo y alimenta un dashboard.

## Estado
- Etapa 1 (recolección): `agent/collect.py`
- Etapa 2 (filtro, extracción con Gemini, verificación): `agent/process.py`
- Cuaderno de Colab para probar sin instalar nada: `notebooks/radar_salud_colab_v3.ipynb`
- Registro de uso de IA: `docs/registro_uso_ia.md`
- Pendiente: brechas, dashboard y ejecución diaria automática.

La clave de la API de Gemini **nunca** va en este repositorio (se guarda como secreto).
