# Recolector (etapa 1)
1. Instalar Python 3.9+ (python.org). No hay que instalar librerias.
2. En una terminal, dentro de esta carpeta:  python collect.py --selftest   (debe decir SELFTEST OK)
3. Correr:  python collect.py --days 30   -> muestra una tabla OK/FALLA por fuente
4. Resultado: ../data/raw/raw_items.jsonl (material crudo con fecha, fuente y URL) y run_log.jsonl
Re-ejecutar = volver a correr el paso 3; no duplica items.
