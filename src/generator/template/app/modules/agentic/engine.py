"""Moteur d'orchestration agentic (Chap 15) — généralise le pipeline Studio.

Un service déclare des `steps` (chacun `type: agent | tool`) et des `workflows`
(listes ordonnées de noms de steps). Le moteur exécute un workflow : il enchaîne
les steps, passe un `context` accumulé de l'un à l'autre, persiste chaque étape
(`ExecutionStep`) pour l'audit et la reprise, puis remplit le résultat.

Filiation avec `shared_services/studio/pipeline.py` : sortie structurée, stub
déterministe sans clé (via `call_llm`), trace des étapes. Différences : async,
piloté par la déclaration YAML, et un step peut appeler un **tool** d'API externe
(Suno) plutôt qu'un simple agent LLM.
"""

import asyncio
import json

from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.agentic.llm_client import call_llm
from app.modules.agentic.models import ExecutionStep, ServiceExecution
from app.modules.agentic.tools import get_tool


async def execute_workflow(
    db: AsyncSession,
    execution: ServiceExecution,
    service: dict,
    step_names: list[str],
    params: dict,
) -> ServiceExecution:
    """Exécute les `step_names` du service, en mettant `execution` à jour.

    Renvoie l'exécution (status `completed` ou `failed`). Chaque étape est tracée
    dans `execution_steps`. En cas d'échec d'une étape, on arrête et on marque
    l'exécution `failed` (le job async remboursera alors les crédits).
    """
    steps_def = service.get("steps", {})
    context: dict = {"parameters": params}

    execution.status = "running"
    await db.commit()

    for idx, name in enumerate(step_names):
        sdef = steps_def.get(name, {})
        kind = sdef.get("type", "agent")
        step = ExecutionStep(
            execution_id=execution.id, idx=idx, name=name, kind=kind, status="running"
        )
        db.add(step)
        await db.commit()

        try:
            if kind == "tool":
                tool = get_tool(sdef.get("tool", ""))
                if tool is None:
                    raise ValueError(f"Tool inconnu : {sdef.get('tool')!r}")
                output = await tool(context, sdef)
            else:
                # call_llm est synchrone (réseau en prod) : on le sort du event
                # loop pour ne pas bloquer les autres jobs concurrents.
                output = await asyncio.to_thread(
                    call_llm,
                    sdef.get("model", "claude-sonnet-5"),
                    [
                        {"role": "system", "content": sdef.get("system_prompt", "")},
                        {
                            "role": "user",
                            "content": json.dumps(context, ensure_ascii=False, default=str),
                        },
                    ],
                    sdef.get("temperature", 0.4),
                )
            context[name] = output
            step.status = "completed"
            step.output = output if isinstance(output, dict) else {"text": output}
            await db.commit()
        except Exception as exc:  # noqa: BLE001 — on veut tracer tout échec d'étape
            step.status = "failed"
            step.output = {"error": str(exc)}
            execution.status = "failed"
            execution.result = {"error": str(exc), "failed_step": name}
            await db.commit()
            return execution

    # Résultat : les sorties par étape + un `output` pratique (dernier texte
    # d'agent, ex. les lyrics pour un aperçu Concept).
    result = {k: v for k, v in context.items() if k != "parameters"}
    result["output"] = next(
        (context[n] for n in reversed(step_names) if isinstance(context.get(n), str)),
        "",
    )
    execution.result = result
    execution.status = "completed"
    await db.commit()
    return execution
