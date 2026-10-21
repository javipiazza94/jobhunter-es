"""Borrado de ficheros de backend/inbox/ una vez cargados en job_hunter.db (regla: los datos ya cargados
no se dejan acumulados). Un fichero con filas sin cargar (mal formato, dudosas, «A REVISAR») se conserva."""
from pathlib import Path


def delete_loaded(files: list[str], pending: set[str]) -> None:
    for f in files:
        if f in pending:
            print(f"conservado {Path(f).name}: tiene filas sin cargar (revisarlas y volver a cargar)")
            continue
        Path(f).unlink()
        print(f"borrado {Path(f).name} (ya cargado en la BD)")
