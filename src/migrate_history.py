"""
migrate_history.py — Migração ÚNICA: reclassifica com o prompt v2 os itens
do history.json que foram classificados pelo prompt antigo (identificáveis
por não terem o campo trigger_reason).

O que acontece com cada item legado:
- Itens que a triagem v2 DESCARTA (colunas recorrentes, research, marketing,
  crédito corporativo fora do escopo...) saem do histórico.
- Itens que sobrevivem ganham a classificação nova: trigger_reason,
  confirmation, relevância recalibrada, travas aplicadas.
- Duplicatas semânticas entre legados são fundidas.
Itens já classificados pela v2 não são tocados.

Como rodar (uma vez, na sua máquina, dentro da pasta do projeto):
    Windows:  set DEEPSEEK_API_KEY=sua-chave
              python src/migrate_history.py
    Linux/Mac: DEEPSEEK_API_KEY=sua-chave python src/migrate_history.py

Depois: confira o resumo impresso, e commite o data/history.json atualizado.
Um backup fica em data/history.json.bak — se algo sair estranho, é só
renomear de volta.
"""

import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from synthesize import classify_batch

HISTORY_PATH = Path(__file__).parent.parent / "data" / "history.json"


def main():
    api_key = os.environ.get("DEEPSEEK_API_KEY")
    if not api_key:
        print("Erro: defina a variável de ambiente DEEPSEEK_API_KEY", file=sys.stderr)
        sys.exit(1)

    if not HISTORY_PATH.exists():
        print(f"Erro: {HISTORY_PATH} não encontrado — rode dentro da pasta do projeto", file=sys.stderr)
        sys.exit(1)

    original_text = HISTORY_PATH.read_text(encoding="utf-8")
    history = json.loads(original_text)

    legacy = [i for i in history if "trigger_reason" not in i]
    modern = [i for i in history if "trigger_reason" in i]

    print(f"Histórico: {len(history)} itens — {len(legacy)} legados (prompt antigo), {len(modern)} já na v2")
    if not legacy:
        print("Nada a migrar.")
        return

    # IMPORTANTE: sem known_titles aqui — os legados casariam com eles mesmos
    # e o modelo descartaria tudo.
    reclassified = classify_batch(legacy, api_key)
    reclassified = [c for c in reclassified if c.get("relevance") != "baixa"]

    kept_titles = {c["title"] for c in reclassified}
    discarded = [i["title"] for i in legacy if i["title"] not in kept_titles]

    backup = HISTORY_PATH.with_suffix(".json.bak")
    backup.write_text(original_text, encoding="utf-8")

    new_history = modern + reclassified
    new_history.sort(key=lambda i: i["published_at"])
    HISTORY_PATH.write_text(json.dumps(new_history, ensure_ascii=False, indent=2), encoding="utf-8")

    triggers = sum(1 for i in reclassified if i.get("daily_trigger"))
    print(f"\nReclassificados: {len(legacy)} legados → {len(reclassified)} mantidos "
          f"({triggers} com gatilho), {len(discarded)} descartados/fundidos:")
    for t in discarded:
        print(f"  - {t[:90]}")
    print(f"\nHistórico novo: {len(new_history)} itens. Backup em {backup.name}.")
    print("Agora: git add data/history.json && git commit -m \"Reclassifica historico com prompt v2\" && git push")


if __name__ == "__main__":
    main()
