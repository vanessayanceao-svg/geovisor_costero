# Scripts de evidencia de la auditoría (25‑10‑2026)

Scripts independientes con los que se verificó el motor de cálculo (`src/calculo`) frente a DSAS v6.1, a implementaciones de referencia (scipy/sklearn) y a casos sintéticos. Las salidas `salida_*.txt` son las obtenidas durante la auditoría. Para repetirlos:

```bash
cd geovisor_costero
python docs/auditoria_scripts/run_e2e.py        # corrida completa → docs/auditoria_scripts/_trabajo/e2e.pkl
python docs/auditoria_scripts/check_dsas.py     # tasas e intersecciones vs DSAS (ajuste la ruta D en la cabecera si hace falta)
python docs/auditoria_scripts/check_units.py    # EWM, FAHP, TOPSIS, Spearman, κ, VIF contra referencias
python docs/auditoria_scripts/check_muestreo.py # estadísticos zonales con rásteres/vectores sintéticos
python docs/auditoria_scripts/check_proy.py     # ventanas, bloques, R²_OS, Bruun, tasaL
python docs/auditoria_scripts/check_edges.py    # casos límite
```

Las pruebas de regresión equivalentes, ya integradas en la suite, están en `tests/test_auditoria.py`.
