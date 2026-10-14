"""Interactive Cloud specification reads only; no local writes or key exports."""
import json
from pathlib import Path
import sys
import tkinter as tk
from tkinter import messagebox, simpledialog

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from smart_tray.diagnostic import cloud_connection, quiet, safe_constraints


def main():
    root = tk.Tk()
    root.withdraw()
    try:
        region = simpledialog.askstring("Especificação, somente leitura", "Data center do projeto Smart Life (ex.: us):", parent=root)
        api_id = simpledialog.askstring("Especificação, somente leitura", "Access ID / Client ID (somente em memória):", show="•", parent=root)
        secret = simpledialog.askstring("Especificação, somente leitura", "Access Secret / Client Secret (somente em memória):", show="•", parent=root)
        if not region or not api_id or not secret:
            return
        path = ROOT / "diagnostics/provisioned.json"
        registry = json.loads(path.read_text(encoding="utf-8"))
        outcomes = []
        with cloud_connection(region.strip(), api_id, secret) as cloud:
            for record in registry["devices"]:
                if record["role"] not in {"led", "novadigital"}:
                    continue
                try:
                    response = cloud.getdps(record["device_id"])
                    if not isinstance(response, dict) or not response.get("success"):
                        raise RuntimeError
                    schema = response.get("result", {})
                    for section in ("status", "functions"):
                        for item in schema.get(section, []):
                            for existing in record["metadata"].get("cloud_dps_candidates", []):
                                if str(existing["dp_id"]) == str(item.get("dp_id")) and existing["code"] == item.get("code") and existing["source"] == "cloud_" + section:
                                    existing["constraints"] = safe_constraints(item.get("values"), (api_id, secret, cloud.token))
                    outcomes.append({"role": record["role"], "result": "schema_read_ok"})
                except Exception:
                    outcomes.append({"role": record["role"], "result": "schema_read_pending"})
        path.write_text(json.dumps(registry, ensure_ascii=False, indent=2), encoding="utf-8")
        (ROOT / "diagnostics/specification-check.json").write_text(json.dumps(outcomes, indent=2), encoding="utf-8")
        messagebox.showinfo("Especificação", "Consulta encerrada. Apenas intervalos/enumerações permitidos foram gravados. Nenhum controle foi enviado.", parent=root)
    except Exception:
        messagebox.showerror("Especificação", "Consulta não concluída. Confira projeto, serviços e região. Nenhum erro bruto foi registrado.", parent=root)
    finally:
        root.destroy()


if __name__ == "__main__":
    with quiet():
        main()
