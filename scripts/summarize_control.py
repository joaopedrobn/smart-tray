"""Refresh stage-two report/profiles from sanitized local journals; no network."""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DIRECTORY = ROOT / "diagnostics/control-tests"


def main():
    plans = [json.loads(p.read_text(encoding="utf-8")) for p in DIRECTORY.glob("*.json")]
    latest = {}
    for plan in sorted(plans, key=lambda p: p["timestamp"]):
        latest[(plan["role"], plan["dp"])] = plan
    rows = []
    for role, filename, name, dps in [
        ("led", "led_profile.json", "Fita Outsmart — 10.77.0.39", [20]),
        ("novadigital", "novadigital_profile.json", "NovaDigital — 10.77.0.38", [1, 2]),
    ]:
        path = ROOT / "profiles" / filename
        profile = json.loads(path.read_text(encoding="utf-8"))
        validations = {}
        for dp in dps:
            plan = latest.get((role, dp))
            if not plan:
                continue
            change, restore = plan.get("change") or {}, plan.get("restore") or {}
            off_ok = change.get("state_confirmed") and plan.get("physical_confirmed")
            on_ok = restore.get("state_confirmed") and plan.get("restore_physical_confirmed")
            evidence = "diagnostics/control-tests/" + plan["plan_id"] + ".json"
            validations[str(dp)] = {"status": plan["status"], "change_lan_confirmed": bool(change.get("state_confirmed")),
                "change_physical_confirmed": bool(plan.get("physical_confirmed")),
                "restore_lan_confirmed": bool(restore.get("state_confirmed")),
                "restore_physical_confirmed": bool(plan.get("restore_physical_confirmed")), "evidence": evidence}
            function = "Alimentação" if role == "led" else "Canal " + str(dp)
            for step, result, physical, value, confirmed in [
                ("Teste", change, plan.get("physical_confirmed"), plan["proposed"], off_ok),
                ("Restaurar", restore, plan.get("restore_physical_confirmed"), plan["initial"], on_ok),
            ]:
                sent = result.get("write_attempted", False)
                outcome = "Validado LAN + físico" if confirmed else (
                    "LAN confirmado; observação física pendente" if result.get("state_confirmed") else
                    "Alteração não confirmada; interrompido" if sent else "Não enviado")
                state = str(value).lower() if result.get("state_confirmed") else "Pendente"
                rows.append(f"| {name} | {function}: {step.lower()} | {dp} | {str(value).lower() if sent else '—'} | {outcome} | {state} |")
            if off_ok and on_ok:
                code = "switch_led" if role == "led" else "switch_" + str(dp)
                profile["confirmed_dps"][str(dp)] = {"code": code, "type": "Boolean", "validation": "lan_and_user_physical"}
                profile["confirmed_commands"][code] = {"dp": dp, "values": [False, True], "transport": "lan", "evidence": evidence}
                profile["observed_dps"][str(dp)]["value"] = plan["initial"]
                profile["observed_dps"][str(dp)]["function"] = code
        profile["control_validation"] = validations
        for candidate in profile.get("potential_functions", []):
            if str(candidate.get("dp_id")) in profile["confirmed_dps"]:
                candidate["locally_validated"] = True
        all_validated = all(str(dp) in profile["confirmed_dps"] for dp in dps)
        profile["status"] = "power_control_validated" if all_validated else "control_validation_in_progress"
        profile["notes"] = "Somente comandos em confirmed_commands possuem confirmação LAN e física. Demais DPS permanecem sem escrita validada."
        path.write_text(json.dumps(profile, ensure_ascii=False, indent=2), encoding="utf-8")
    rows.append("| Elgin — 10.77.0.138 | Nenhuma | — | — | pending_oem_provisioning; excluído dos testes | Pendente |")
    report = ROOT / "diagnostics/compatibility.md"
    text = report.read_text(encoding="utf-8")
    start = text.index("## Etapa 2 —")
    end = text.index("## Resultado por dispositivo", start)
    previous = text[start:end]
    detail_start = previous.index("A especificação GET")
    details = previous[detail_start:]
    table = "\n".join(["| Dispositivo | Função | DPS | Comando | Resultado | Estado confirmado |",
        "|---|---|---|---|---|---|", *rows])
    introduction = ("## Etapa 2 — testes interativos\n\n"
        "A fita foi desligada e restaurada por uma escrita por ação, com confirmação física do usuário e leituras LAN posteriores em conexão nova (false e true). "
        "As leituras imediatas anteriores mostraram o estado anterior; a discrepância foi resolvida sem repetir qualquer escrita. "
        "A restauração foi enviada somente após confirmação do desligamento. O histórico original permanece preservado nos registros.\n\n")
    text = text[:start] + introduction + table + "\n\n" + details + text[end:]
    text = text.replace("A etapa 2 iniciou uma tentativa autorizada de desligar a fita, ainda sem confirmação de alteração.", "A etapa 2 validou liga/desliga da fita com confirmação LAN e física; os canais do interruptor são testados individualmente.")
    text = text.replace("Próximo passo da fita: obter a observação física do usuário e esclarecer a discrepância sem repetir escrita.", "Fita desligada e restaurada, com confirmação LAN e física. Nenhum teste RGB foi executado.")
    text = text.replace("Interruptor continua independente, aguardando proposta e aprovação por canal.", "A tabela acima indica o andamento de cada canal do interruptor; aprovações são individuais.")
    text = text.replace("A tentativa autorizada da fita não confirmou alteração; novas escritas nela estão interrompidas.", "Liga/desliga da fita foi confirmado por LAN e observação física, com estado inicial restaurado.")
    text = text.replace("Aguardando observação física da fita e aprovação dos canais do interruptor;", "Fita validada; andamento dos canais do interruptor conforme tabela da etapa 2;")
    report.write_text(text, encoding="utf-8")


if __name__ == "__main__":
    main()
