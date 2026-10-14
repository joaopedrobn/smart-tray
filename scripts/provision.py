"""Local provisioning dialog. No wizard, plaintext keys or command arguments."""
import argparse
import json
from pathlib import Path
import sys
import tkinter as tk
from tkinter import messagebox, simpledialog

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from smart_tray.security import CredentialStore
from smart_tray.diagnostic import cloud_connection, collect_device, mask, quiet, clean_text


def main():
    global ROOT
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manual", action="store_true")
    parser.add_argument('--config-root', type=Path, help='Private device configuration directory')
    parser.add_argument("--role", choices=("elgin", "led", "novadigital"), help="Provision only this identified device; preserve peers")
    parser.add_argument("--include-oem", action="store_true", help="Include OEM devices only after their account is linked")
    args = parser.parse_args()
    if args.config_root:
        ROOT = args.config_root.resolve()
    root = tk.Tk()
    root.withdraw()
    path = ROOT / "diagnostics/provisioned.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    existing = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {"devices": []}
    by_id = {r["device_id"]: r for r in existing["devices"]}
    # Only devices already identified/registered by the user; never the two unknown IDs.
    records = list(by_id.values())
    if args.role:
        records = [r for r in records if r.get("role") == args.role]
    store = CredentialStore()
    for record in records:
        if record.get("role") == "elgin" and record.get("app") != "Smart Life" and not args.include_oem and not args.manual:
            record["provisioning_status"] = "pending_oem_provisioning"
    path.write_text(json.dumps({"devices": list(by_id.values())}, ensure_ascii=False, indent=2), encoding="utf-8")
    records = [r for r in records if args.include_oem or args.manual or r.get("role") != "elgin" or r.get("app") == "Smart Life"]

    def accept(record, metadata, key):
        known = by_id.get(record["device_id"])
        metadata = {**(known or {}).get("metadata", {}), **{k: v for k, v in metadata.items() if v is not None}}
        label = f'{mask(record["device_id"])} / {record["ip"]}\nNome: {metadata.get("name")}\nProduto: {metadata.get("product_name")}\nCategoria: {metadata.get("category")}'
        availability = "disponível para armazenamento DPAPI" if key else "pendente na API"
        verified = known and known.get("identity_evidence") == "official_app_id_and_mac_match_discovery_and_arp"
        if not verified and not messagebox.askyesno("Confirmar aparelho", label + f"\nCredencial: {availability}\n\nVocê reconhece este dispositivo como seu e deseja cadastrá-lo para leitura LAN?", parent=root):
            return
        role = known["role"] if verified else simpledialog.askstring("Associação", "Se confirmado no aplicativo, informe: elgin, novadigital, led ou outro. Cancelar mantém sem associação.", parent=root)
        if role not in {"elgin", "novadigital", "led", "outro"}:
            return
        if any(r.get("role") == role and did != record["device_id"] for did, r in by_id.items()) and role != "outro":
            messagebox.showerror("Associação", "Já existe um dispositivo associado a essa função. Revise antes de continuar.", parent=root)
            return
        if key:
            store.save(record["device_id"], key)
        by_id[record["device_id"]] = {**record, "metadata": metadata, "role": role,
                                      "identity_evidence": known["identity_evidence"] if verified else ("exact_cloud_id_and_user_confirmation" if not args.manual else "user_app_confirmation"),
                                      "credential": "available_dpapi" if key else known.get("credential", "pending"),
                                      "provisioning_status": "provisioned" if key else ("pending_oem_provisioning" if role == "elgin" else "pending_credentials"),
                                      "local_read": "pending"}
        path.write_text(json.dumps({"devices": list(by_id.values())}, ensure_ascii=False, indent=2), encoding="utf-8")

    try:
        if not records:
            messagebox.showwarning("Identificação pendente", "Nenhum aparelho identificado foi cadastrado. Conclua primeiro a associação por ID/MAC.", parent=root)
            return
        if args.manual:
            for record in records:
                if not messagebox.askyesno("Importar chave", f'{mask(record["device_id"])} / {record["ip"]}\nPossui identificação e Local_Key deste aparelho?', parent=root):
                    continue
                name = simpledialog.askstring("Nome", "Nome confirmado no aplicativo:", parent=root)
                key = simpledialog.askstring("Local_Key", "Local_Key (armazenada via DPAPI):", show="•", parent=root)
                if name and key:
                    accept(record, {"name": clean_text(name, (key,)), "cloud_dps_candidates": []}, key)
                key = None
        else:
            region = simpledialog.askstring("Data center", "Código do data center do projeto: cn, us, us-e, eu, eu-w, in ou sg", parent=root)
            api_id = simpledialog.askstring("Tuya", "Access ID / Client ID (somente em memória):", show="•", parent=root)
            secret = simpledialog.askstring("Tuya", "Access Secret / Client Secret (somente em memória):", show="•", parent=root)
            if not region or not api_id or not secret:
                return
            with cloud_connection(region.strip(), api_id, secret) as cloud:
                for record in records:
                    metadata, key, outcome = collect_device(cloud, record["device_id"], api_id, secret)
                    if metadata:
                        try:
                            accept(record, metadata, key)
                        except Exception:
                            messagebox.showwarning("Dispositivo pendente", f'{mask(record["device_id"])}: cadastro não concluído. Os demais aparelhos continuarão.', parent=root)
                    if not metadata or not key:
                        messagebox.showwarning("Provisionamento pendente", f'{mask(record["device_id"])}: API sem metadados ou Local_Key. Verifique vínculo, serviços e região.', parent=root)
                    key = None
            api_id = secret = None
        messagebox.showinfo("Provisionamento", "Coleta encerrada. Somente chaves DPAPI e metadados permitidos foram armazenados. Nenhum controle foi enviado.", parent=root)
    except Exception:
        # Never show exception text, cloud response or traceback with credentials.
        messagebox.showerror("Provisionamento", "Não foi possível concluir. Verifique formato da chave, permissões da API, data center e conexão. Nenhum erro bruto foi registrado.", parent=root)
    finally:
        root.destroy()


if __name__ == "__main__":
    with quiet():
        main()
